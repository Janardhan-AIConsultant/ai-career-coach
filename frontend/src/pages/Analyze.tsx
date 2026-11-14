import { useRef, useState } from "react";
import { download, messageOf, request } from "../api/http";
import { Button, Card, ErrorBox, Field, List, Notice, inputCls } from "../components/ui";
import { useSession } from "../store/session";

/* Minimal shapes of the responses this page reads (the server schemas are larger). */
interface Doc { document_id: string; injection_flagged?: boolean | null }
interface Skill { skill: string }
interface Resume {
  quality: { score: number; note: string };
  experience_summary: string;
  technical_skills: Skill[];
  strengths: string[];
  weaknesses: string[];
  ats_recommendations: string[];
}
interface Jd {
  title: string | null;
  mandatory_skills: string[];
  preferred_skills: string[];
  optional_skills: string[];
  responsibilities: string[];
}
interface Match {
  overall_score: number;
  disclaimer?: string;
  category_scores: { category: string; score: number | null; weight: number; detail: string }[];
  matching_skills: { skill: string }[];
  partial_skills: { skill: string; related_resume_skill: string | null }[];
  missing_skills: { skill: string; level: string }[];
  recommendations: string[];
}
interface Gap {
  skill: string;
  severity: string;
  status: string;
  suggested_timeline_days: number;
  current_evidence: string;
  learning_recommendations: string[];
}
interface GapAnalysis { gaps: Gap[]; summary: string; note?: string }
interface Change { id: string; section: string; change_type: string; before: string; after: string; reason: string; applied: boolean }
interface Optim {
  optimized_resume_text: string;
  changes: Change[];
  pending_approval_ids: string[];
  needs_confirmation: string[];
  clarification_questions: string[];
  note?: string;
}
interface Outputs { resume?: Resume; jd?: Jd; match?: Match; gap?: GapAnalysis; opt?: Optim }

type Tab = "resume" | "jd" | "match" | "gap" | "optimize";
const TABS: [Tab, string][] = [
  ["resume", "Resume analysis"],
  ["jd", "Job description"],
  ["match", "Match"],
  ["gap", "Skill gap"],
  ["optimize", "Optimise resume"],
];

export default function Analyze() {
  const user = useSession((s) => s.user);
  const setGuestToken = useSession((s) => s.setGuestToken);
  const guest = !user;
  const ws = guest ? "/guest" : "";
  const auth = guest ? "guest" : "user";

  const [tab, setTab] = useState<Tab>("resume");
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [resumeDoc, setResumeDoc] = useState<Doc | null>(null);
  const [jdDoc, setJdDoc] = useState<Doc | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [wantReport, setWantReport] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [out, setOut] = useState<Outputs>({});
  const [approved, setApproved] = useState<string[]>([]);
  const analysed = useRef(new Set<string>());

  const needsResume = tab !== "jd";
  const needsJd = tab !== "resume";
  const hasResume = resumeText.trim().length > 0 || resumeDoc !== null;
  const hasJd = jdText.trim().length > 0 || jdDoc !== null;
  const canRun = (!needsResume || hasResume) && (!needsJd || hasJd);

  const ensureGuest = async () => {
    // read the store, not the render-time value: two uploads in one run must share one session
    if (!guest || useSession.getState().guestToken) return;
    const s = await request<{ token: string }>("/guest/sessions", { method: "POST", auth: "none" });
    setGuestToken(s.token);
  };

  const upload = async (kind: "resume" | "job_description", text: string): Promise<Doc> => {
    await ensureGuest();
    const form = new FormData();
    form.set("kind", kind);
    form.set("text", text);
    return request<Doc>(`${ws}/documents`, { form, auth: useSession.getState().user ? "user" : "guest" });
  };

  const analyse = async () => {
    setBusy(true);
    setError(null);
    try {
      let r = resumeDoc;
      let j = jdDoc;
      if (needsResume && !r) {
        r = await upload("resume", resumeText);
        setResumeDoc(r);
      }
      if (needsJd && !j) {
        j = await upload("job_description", jdText);
        setJdDoc(j);
      }
      const fmt = wantReport ? { report_format: "pdf" } : {};
      const call = <T,>(path: string, json: object, withReport = true) =>
        request<T & { report_id?: string | null }>(`${ws}${path}`, { json: { ...json, ...(withReport ? fmt : {}) }, auth });
      const pair = { resume_document_id: r?.document_id, job_description_document_id: j?.document_id };
      // The server keeps the parsed text of a document only after it has been analysed once, so the
      // match, skill-gap and optimise services need both analyses to exist first.
      if (needsResume && tab !== "resume" && r && !analysed.current.has(r.document_id)) {
        await call<{ analysis: Resume }>("/resume/analyze", { document_id: r.document_id }, false);
        analysed.current.add(r.document_id);
      }
      if (needsJd && tab !== "jd" && j && !analysed.current.has(j.document_id)) {
        await call<{ analysis: Jd }>("/job-description/analyze", { document_id: j.document_id }, false);
        analysed.current.add(j.document_id);
      }
      if (tab === "resume") {
        const res = await call<{ analysis: Resume }>("/resume/analyze", { document_id: r?.document_id });
        setOut((o) => ({ ...o, resume: res.analysis }));
        if (r) analysed.current.add(r.document_id);
        setReport(res.report_id ?? null);
      } else if (tab === "jd") {
        const res = await call<{ analysis: Jd }>("/job-description/analyze", { document_id: j?.document_id });
        setOut((o) => ({ ...o, jd: res.analysis }));
        if (j) analysed.current.add(j.document_id);
        setReport(res.report_id ?? null);
      } else if (tab === "match") {
        const res = await call<{ match: Match }>("/career/match", pair);
        setOut((o) => ({ ...o, match: res.match }));
        setReport(res.report_id ?? null);
      } else if (tab === "gap") {
        const res = await call<{ analysis: GapAnalysis }>("/career/skill-gap", pair);
        setOut((o) => ({ ...o, gap: res.analysis }));
        setReport(res.report_id ?? null);
      } else {
        const res = await call<{ result: Optim }>("/resume/optimize", { ...pair, approved_change_ids: approved });
        setOut((o) => ({ ...o, opt: res.result }));
        setReport(res.report_id ?? null);
      }
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <h1 className="mb-2 text-2xl font-bold">Analyse your resume and target job</h1>
      {guest && (
        <Notice>
          You are using a temporary guest session. Your documents are deleted when it expires and nothing is saved to an
          account. <a className="underline" href="/register">Register</a> to keep your history.
        </Notice>
      )}
      <div role="tablist" className="mb-3 flex flex-wrap gap-1">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            role="tab"
            aria-selected={tab === id}
            onClick={() => setTab(id)}
            className={`rounded border px-3 py-1 text-sm ${tab === id ? "bg-blue-600 text-white" : "bg-white"}`}
          >
            {label}
          </button>
        ))}
      </div>
      <ErrorBox error={error} />
      <Card>
        {needsResume && (
          <Field label="Resume text">
            <textarea
              className={inputCls}
              rows={7}
              maxLength={100000}
              value={resumeText}
              placeholder="Paste your resume"
              onChange={(e) => {
                setResumeText(e.target.value);
                setResumeDoc(null);
              }}
            />
          </Field>
        )}
        {needsJd && (
          <Field label="Job description text">
            <textarea
              className={inputCls}
              rows={7}
              maxLength={100000}
              value={jdText}
              placeholder="Paste the job description"
              onChange={(e) => {
                setJdText(e.target.value);
                setJdDoc(null);
              }}
            />
          </Field>
        )}
        {(resumeDoc?.injection_flagged || jdDoc?.injection_flagged) && (
          <Notice>
            This document contains text that looks like instructions to an AI. It was treated as plain data and ignored.
          </Notice>
        )}
        <label className="mb-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={wantReport} onChange={(e) => setWantReport(e.target.checked)} />
          Also create a PDF report
        </label>
        <Button busy={busy} disabled={!canRun} onClick={analyse}>
          Run analysis
        </Button>
        {report && (
          <button
            className="ml-3 text-sm text-blue-700 underline"
            onClick={() => download(`${ws}/reports/${report}/download`, "report.pdf", { auth }).catch((e) => setError(messageOf(e)))}
          >
            Download report
          </button>
        )}
      </Card>

      {tab === "resume" && out.resume && (
        <Card title="Resume analysis">
          <p className="mb-2 text-sm">{out.resume.experience_summary}</p>
          <p className="mb-2 text-sm">
            <b>Quality (heuristic):</b> {out.resume.quality.score}/100. {out.resume.quality.note}
          </p>
          <h3 className="font-medium">Skills found</h3>
          <p className="mb-2 text-sm">{out.resume.technical_skills.map((s) => s.skill).join(", ") || "None detected"}</p>
          <h3 className="font-medium">Strengths</h3>
          <List items={out.resume.strengths} />
          <h3 className="mt-2 font-medium">Weaknesses</h3>
          <List items={out.resume.weaknesses} />
          <h3 className="mt-2 font-medium">ATS recommendations</h3>
          <List items={out.resume.ats_recommendations} />
        </Card>
      )}
      {tab === "jd" && out.jd && (
        <Card title={`Job description: ${out.jd.title ?? "untitled role"}`}>
          <h3 className="font-medium">Mandatory</h3>
          <List items={out.jd.mandatory_skills} />
          <h3 className="mt-2 font-medium">Preferred</h3>
          <List items={out.jd.preferred_skills} />
          <h3 className="mt-2 font-medium">Optional</h3>
          <List items={out.jd.optional_skills} />
          <h3 className="mt-2 font-medium">Responsibilities</h3>
          <List items={out.jd.responsibilities} />
        </Card>
      )}
      {tab === "match" && out.match && (
        <Card title="Match estimate">
          <p className="mb-1 text-3xl font-bold" aria-label="Overall match score">
            {out.match.overall_score}/100
          </p>
          {out.match.disclaimer && <p className="mb-2 text-xs text-gray-600">{out.match.disclaimer}</p>}
          <table className="mb-3 w-full text-sm">
            <thead>
              <tr className="text-left">
                <th>Category</th>
                <th>Score</th>
                <th>Weight</th>
                <th>Detail</th>
              </tr>
            </thead>
            <tbody>
              {out.match.category_scores.map((c) => (
                <tr key={c.category} className="border-t">
                  <td>{c.category}</td>
                  <td>{c.score ?? "n/a"}</td>
                  <td>{c.weight}</td>
                  <td>{c.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 className="font-medium">Matching</h3>
          <List items={out.match.matching_skills.map((s) => s.skill)} />
          <h3 className="mt-2 font-medium">Partial</h3>
          <List items={out.match.partial_skills.map((s) => `${s.skill} (you show ${s.related_resume_skill ?? "related skills"})`)} />
          <h3 className="mt-2 font-medium">Missing</h3>
          <List items={out.match.missing_skills.map((s) => `${s.skill} (${s.level})`)} />
          <h3 className="mt-2 font-medium">Recommendations</h3>
          <List items={out.match.recommendations} />
        </Card>
      )}
      {tab === "gap" && out.gap && (
        <Card title="Skill gaps">
          <p className="mb-2 text-sm">{out.gap.summary}</p>
          {out.gap.gaps.map((g) => (
            <div key={g.skill} className="mb-2 rounded border p-2 text-sm">
              <b>{g.skill}</b> · {g.severity} · {g.status.replace("_", " ")} · about {g.suggested_timeline_days} days
              <p className="text-gray-600">{g.current_evidence}</p>
              <List items={g.learning_recommendations} />
            </div>
          ))}
          {out.gap.note && <p className="text-xs text-gray-600">{out.gap.note}</p>}
        </Card>
      )}
      {tab === "optimize" && out.opt && (
        <Card title="Optimised resume">
          {out.opt.note && <Notice>{out.opt.note}</Notice>}
          {out.opt.clarification_questions.length > 0 && (
            <>
              <h3 className="font-medium">Questions for you</h3>
              <List items={out.opt.clarification_questions} />
            </>
          )}
          <h3 className="mt-2 font-medium">Changes</h3>
          {out.opt.changes.map((c) => (
            <div key={c.id} className="mb-2 rounded border p-2 text-sm">
              <b>{c.section}</b> · {c.change_type} · {c.applied ? "applied" : "needs your approval"}
              <p className="text-gray-600">Before: {c.before || "(empty)"}</p>
              <p>After: {c.after}</p>
              <p className="text-xs text-gray-500">{c.reason}</p>
              {!c.applied && (
                <label className="mt-1 flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={approved.includes(c.id)}
                    onChange={(e) => setApproved((a) => (e.target.checked ? [...a, c.id] : a.filter((x) => x !== c.id)))}
                  />
                  Approve this change, then run again
                </label>
              )}
            </div>
          ))}
          <h3 className="mt-2 font-medium">Resulting text</h3>
          <pre className="whitespace-pre-wrap rounded bg-gray-100 p-2 text-sm">{out.opt.optimized_resume_text}</pre>
        </Card>
      )}
    </>
  );
}
