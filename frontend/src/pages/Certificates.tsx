import { FormEvent, useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { download, messageOf, request } from "../api/http";
import { Button, Card, ErrorBox, Field, Notice, Spinner, inputCls, PageHeader } from "../components/ui";
import { useSession } from "../store/session";

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
      <PageHeader title="Certificates" />
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


const SAMPLES = [
  { src: "/samples/certificate-learning.png", title: "Learning completion", how: "Finish a 7, 15 or 60 day roadmap, including every assessment it contains." },
  { src: "/samples/certificate-assessment.png", title: "Assessment", how: "Pass an assessment. Your score is printed on the certificate." },
  { src: "/samples/certificate-project.png", title: "Project completion", how: "Submit a GitHub project that passes the automated review." },
];

/** Illustrations only: watermarked, placeholder name, and an ID that can never verify. */
function SampleCertificates() {
  const user = useSession((s) => s.user);
  return (
    <section aria-labelledby="samples" className="mt-8">
      <h2 id="samples" className="mb-1 text-xl font-bold">What you can earn</h2>
      <p className="mb-4 text-sm text-slate-600">
        Three kinds of certificate, each issued from your own verified progress. These are <b>samples</b> to show the
        design: they are watermarked, use a placeholder name and cannot be verified.
      </p>
      <div className="grid gap-5 md:grid-cols-3">
        {SAMPLES.map((c) => (
          <figure key={c.src} className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <a href={c.src} target="_blank" rel="noopener noreferrer" aria-label={`Open the sample ${c.title} certificate full size`}>
              <img src={c.src} alt={`Sample ${c.title} certificate (not a real certificate)`} loading="lazy" className="w-full border-b border-slate-100" />
            </a>
            <figcaption className="p-4 text-sm">
              <p className="font-semibold text-slate-900">{c.title}</p>
              <p className="mt-1 text-slate-600">{c.how}</p>
            </figcaption>
          </figure>
        ))}
      </div>
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <Link to={user ? "/certificates" : "/register"} className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">
          {user ? "See what I can claim" : "Register and start earning yours"}
        </Link>
        <span className="text-xs text-slate-500">Certificates are platform-issued, not externally accredited.</span>
      </div>
    </section>
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
      <PageHeader title="Verify a certificate" />
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
      <SampleCertificates />
    </>
  );
}
