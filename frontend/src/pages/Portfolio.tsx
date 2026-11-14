import { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { messageOf, request } from "../api/http";
import { Button, Card, ErrorBox, Field, Notice, Spinner, inputCls, PageHeader } from "../components/ui";

interface Item { id: string; kind: string; title: string; evidence_level: string; skills: string[]; achieved_at: string; is_visible: boolean }
interface Settings {
  visibility: "private" | "public"; public_slug: string | null; public_url: string | null;
  display_name: string | null; headline: string | null; summary: string | null; resume_integration_approved: boolean;
}
interface Portfolio {
  settings: Settings; timeline: Item[]; disclaimer: string;
  skills: { skill: string; highest: string }[];
  stats: { learning_paths_completed: number; assessments_passed: number; certificates: number; projects_passed: number };
}

export function PortfolioPage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portfolio"], queryFn: () => request<Portfolio>("/portfolio") });
  const [name, setName] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const save = useMutation({
    mutationFn: (body: object) => request<Portfolio>("/portfolio/settings", { method: "PUT", json: body }),
    onSuccess: (d) => qc.setQueryData(["portfolio"], d),
  });
  const toggle = useMutation({
    mutationFn: (v: { id: string; is_visible: boolean }) => request<Portfolio>(`/portfolio/items/${v.id}`, { method: "PATCH", json: { is_visible: v.is_visible } }),
    onSuccess: (d) => qc.setQueryData(["portfolio"], d),
  });
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorBox error={messageOf(q.error)} />;
  const p = q.data;
  const s = p.settings;
  const displayName = name ?? s.display_name ?? "";
  const err = save.error ?? toggle.error;

  return (
    <>
      <PageHeader title="Career achievement portfolio" />
      <Notice>{p.disclaimer}</Notice>
      <ErrorBox error={err ? messageOf(err) : null} />
      <Card title="Sharing">
        <p className="mb-2 text-sm">
          Your portfolio is <b>{s.visibility}</b>. {s.visibility === "private" ? "Only you can see it." : `Public link: ${s.public_url}`}
        </p>
        <Field label="Public display name (required to publish)">
          <input className={inputCls} maxLength={80} value={displayName} onChange={(e) => setName(e.target.value)} />
        </Field>
        {s.visibility === "private" ? (
          <>
            <label className="mb-3 flex items-start gap-2 text-sm">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
              I consent to publishing my visible achievements at a public link. I can switch back to private at any time.
            </label>
            <Button disabled={!consent || !displayName.trim()} busy={save.isPending}
              onClick={() => save.mutate({ visibility: "public", consent_public: true, display_name: displayName })}>
              Make public
            </Button>
          </>
        ) : (
          <>
            <Button busy={save.isPending} onClick={() => save.mutate({ visibility: "private" })}>Make private</Button>
            <button className="ml-3 text-sm text-blue-700 underline" onClick={() => request("/portfolio/rotate-slug", { method: "POST" }).then(() => qc.invalidateQueries({ queryKey: ["portfolio"] }))}>
              Change public link
            </button>
          </>
        )}
      </Card>
      <Card title="Achievements">
        {p.timeline.length === 0 && <p className="text-sm text-gray-500">Nothing yet. Achievements appear automatically as you complete verified work.</p>}
        {p.timeline.map((i) => (
          <div key={i.id} className="flex items-start gap-2 border-t py-2 text-sm">
            <input type="checkbox" aria-label={`Show on public page: ${i.title}`} checked={i.is_visible}
              onChange={(e) => toggle.mutate({ id: i.id, is_visible: e.target.checked })} />
            <span>
              <b>{i.title}</b> · {i.kind.replace("_", " ")} · {i.evidence_level === "demonstrated" ? "practically demonstrated" : i.evidence_level}
              {i.skills.length > 0 && <span className="text-gray-600"> · {i.skills.join(", ")}</span>}
            </span>
          </div>
        ))}
      </Card>
    </>
  );
}

interface PublicP {
  display_name: string; headline: string | null; summary: string | null; disclaimer: string;
  timeline: { kind: string; title: string; evidence_level: string; achieved_at: string }[];
  skills: { skill: string; highest: string }[];
}

/** Public page. Private, withdrawn and unknown portfolios all render the same "not found". */
export function PublicPortfolio() {
  const { slug = "" } = useParams();
  const q = useQuery({ queryKey: ["pubp", slug], retry: false, queryFn: () => request<PublicP>(`/portfolio/public/${encodeURIComponent(slug)}`, { auth: "none" }) });
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <p role="alert">This portfolio is not available.</p>;
  const p = q.data;
  return (
    <>
      <h1 className="text-2xl font-bold">{p.display_name}</h1>
      {p.headline && <p className="text-gray-700">{p.headline}</p>}
      {p.summary && <p className="my-2 text-sm">{p.summary}</p>}
      <Notice>{p.disclaimer}</Notice>
      <Card title="Skills">
        <p className="text-sm">{p.skills.map((s) => `${s.skill} (${s.highest === "demonstrated" ? "practically demonstrated" : s.highest})`).join(", ") || "None shown"}</p>
      </Card>
      <Card title="Achievements">
        {p.timeline.map((i, n) => (
          <p key={n} className="border-t py-1 text-sm first:border-0">
            {new Date(i.achieved_at).toLocaleDateString()} · <b>{i.title}</b> · {i.kind.replace("_", " ")}
          </p>
        ))}
      </Card>
    </>
  );
}
