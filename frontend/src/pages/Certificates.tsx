import { FormEvent, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { download, messageOf, request } from "../api/http";
import { Button, Card, ErrorBox, Field, Notice, Spinner, inputCls } from "../components/ui";

interface Cert {
  certificate_id: string; certificate_type: string; title: string; learner_name: string;
  score: number | null; status: string; issued_at: string; verification_url: string; notice: string;
}
interface Eligible { certificate_type: string; source_id: string; label: string; score: number | null }

export function Certificates() {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const list = useQuery({ queryKey: ["certs"], queryFn: () => request<Cert[]>("/certificates") });
  const elig = useQuery({ queryKey: ["elig"], queryFn: () => request<Eligible[]>("/certificates/eligibility") });
  const issue = useMutation({
    mutationFn: (e: Eligible) =>
      request<Cert>("/certificates", { json: { certificate_type: e.certificate_type, source_id: e.source_id, learner_name: name || undefined } }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["certs"] }); void qc.invalidateQueries({ queryKey: ["elig"] }); },
  });
  return (
    <>
      <h1 className="mb-3 text-2xl font-bold">Certificates</h1>
      <Notice>Certificates are issued by this platform from your verified records. They are not externally accredited.</Notice>
      <ErrorBox error={issue.error ? messageOf(issue.error) : null} />
      <Card title="Available to claim">
        <Field label="Name to print (optional; defaults to your display name)">
          <input className={inputCls} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        {elig.isLoading && <Spinner />}
        {elig.data?.length === 0 && <p className="text-sm text-gray-500">Nothing yet. Complete a roadmap, pass an assessment or a project review.</p>}
        {elig.data?.map((e) => (
          <div key={`${e.certificate_type}:${e.source_id}`} className="flex items-center justify-between border-t py-2 text-sm">
            <span>{e.label}{e.score !== null ? ` (${e.score}%)` : ""}</span>
            <Button onClick={() => issue.mutate(e)} busy={issue.isPending}>Issue certificate</Button>
          </div>
        ))}
      </Card>
      <Card title="Your certificates">
        {list.data?.length === 0 && <p className="text-sm text-gray-500">None issued yet.</p>}
        {list.data?.map((c) => (
          <div key={c.certificate_id} className="border-t py-2 text-sm">
            <b>{c.title}</b> · {c.certificate_id} · {c.status}
            <div className="text-xs text-gray-600">Verify at {c.verification_url}</div>
            <button className="text-blue-700 underline" onClick={() => download(`/certificates/${c.certificate_id}/download`, `${c.certificate_id}.pdf`)}>
              Download PDF
            </button>
          </div>
        ))}
      </Card>
    </>
  );
}

/** Public: anyone may check a certificate ID. Invalid and unknown IDs look identical. */
export function Verify() {
  const { id } = useParams();
  const nav = useNavigate();
  const [code, setCode] = useState(id ?? "");
  const q = useQuery({
    queryKey: ["verify", id],
    enabled: !!id,
    retry: false,
    queryFn: () => request<{ status: string; certificate: Cert | null; notice: string }>(`/certificates/verify/${encodeURIComponent(id ?? "")}`, { auth: "none" }),
  });
  const submit = (e: FormEvent) => { e.preventDefault(); if (code.trim()) nav(`/verify/${encodeURIComponent(code.trim())}`); };
  return (
    <>
      <h1 className="mb-3 text-2xl font-bold">Verify a certificate</h1>
      <form onSubmit={submit} className="mb-4 flex max-w-md gap-2">
        <input className={inputCls} aria-label="Certificate ID" placeholder="ACC-XXXX-XXXX-XXXX" value={code} onChange={(e) => setCode(e.target.value)} />
        <Button type="submit">Verify</Button>
      </form>
      {q.isLoading && <Spinner what="Verifying" />}
      {q.error && <p role="alert" className="text-sm">No valid certificate was found for that ID.</p>}
      {q.data && (
        <Card title={q.data.status === "valid" ? "Valid certificate" : "Certificate revoked"}>
          {q.data.certificate && (
            <p className="text-sm">
              {q.data.certificate.title} · issued to {q.data.certificate.learner_name} · {new Date(q.data.certificate.issued_at).toLocaleDateString()}
            </p>
          )}
          <p className="mt-2 text-xs text-gray-600">{q.data.notice}</p>
        </Card>
      )}
    </>
  );
}
