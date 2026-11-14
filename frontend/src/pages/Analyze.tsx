import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { download, messageOf, request } from "../api/http";
import { Bar, Button, Card, Chip, Chips, Empty, ErrorBox, List, Notice, PageHeader, ScoreRing, Stat, type Tone, inputCls } from "../components/ui";
import { useSession } from "../store/session";

/* Minimal shapes of the responses this page reads (the server schemas are larger). */
interface Doc { document_id: string; injection_flagged?: boolean | null }
interface Resume {
  quality: { score: number; note: string };
  experience_summary: string;
  technical_skills: { skill: string }[];
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
  required_competency?: string;
  learning_recommendations: string[];
  practical_exercises?: string[];
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
interface Results { resume?: Resume; jd?: Jd; match?: Match; gap?: GapAnalysis; opt?: Optim }

const SAMPLE_RESUME = `Priya Sharma
Backend developer with 4 years of experience building REST APIs.

Skills: Python, FastAPI, PostgreSQL, SQL, Docker, Git, Redis

Experience
Software Engineer, Acme Payments (2021 - Present)
- Built payment APIs with Python and FastAPI serving 1M requests per day
- Reduced query latency by 35% with PostgreSQL indexing and Redis caching
- Mentored 2 junior developers and ran code reviews

Education
B.Tech in Computer Science`;

const SAMPLE_JD = `Backend Engineer
Requirements: Python, FastAPI, PostgreSQL, Docker, Kafka and Kubernetes.
Preferred: AWS, CI/CD.
Responsibilities: design and build APIs, own services end to end, mentor junior engineers.
Minimum 4 years of experience.`;

const sevTone = (s: string): Tone => (/crit|high|major/i.test(s) ? "red" : /med|mod/i.test(s) ? "amber" : "blue");

function DocInput({ id, title, icon, text, setText, file, setFile, sample, hint }: {
  id: string; title: string; icon: string; text: string; setText: (v: string) => void;
  file: File | null; setFile: (f: File | null) => void; sample: string; hint: string;
}) {
  const pick = useRef<HTMLInputElement>(null);
  return (
    <Card title={title} subtitle={hint} icon={icon} className="mb-0 h-full">
      <textarea
        id={id}
        aria-label={title}
        className={`${inputCls} min-h-[260px] resize-y font-mono text-[13px] leading-5`}
        maxLength={100000}
        value={text}
        disabled={!!file}
        placeholder={file ? `Using the uploaded file: ${file.name}` : "Paste the text here…"}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
        <input ref={pick} type="file" hidden accept=".pdf,.docx,.txt" aria-label={`${title} file`}
          onChange={(e) => { setFile(e.target.files?.[0] ?? null); e.target.value = ""; }} />
        <Button variant="secondary" type="button" onClick={() => pick.current?.click()}>📎 Upload PDF / DOCX / TXT</Button>
        <Button variant="secondary" type="button" onClick={() => { setFile(null); setText(sample); }}>✨ Use sample</Button>
        {(text || file) && <button type="button" className="text-slate-500 underline" onClick={() => { setFile(null); setText(""); }}>Clear</button>}
        <span className="ml-auto text-xs text-slate-400">{file ? file.name : `${text.length.toLocaleString()} characters`}</span>
      </div>
    </Card>
  );
}

export default function Analyze() {
  const user = useSession((s) => s.user);
  const setGuestToken = useSession((s) => s.setGuestToken);
  const guest = !user;
  const ws = guest ? "/guest" : "";
  const authOf = () => (useSession.getState().user ? "user" : "guest") as "user" | "guest";

  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [docs, setDocs] = useState<{ r?: Doc; j?: Doc }>({});
  const [res, setRes] = useState<Results>({});
  const [stage, setStage] = useState<string | null>(null);
  const [optBusy, setOptBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wantReport, setWantReport] = useState(false);
  const [report, setReport] = useState<string | null>(null);
  const [approved, setApproved] = useState<string[]>([]);

  const hasResume = resumeText.trim().length > 0 || resumeFile !== null;
  const hasJd = jdText.trim().length > 0 || jdFile !== null;
  const busy = stage !== null;
  const forget = () => { setDocs({}); setRes({}); setReport(null); setApproved([]); };

  const ensureGuest = async () => {
    // read the store, not a render-time value: two uploads in one run must share one session
    if (!guest || useSession.getState().guestToken) return;
    const s = await request<{ token: string }>("/guest/sessions", { method: "POST", auth: "none" });
    setGuestToken(s.token);
  };

  const upload = async (kind: "resume" | "job_description", text: string, file: File | null): Promise<Doc> => {
    await ensureGuest();
    const form = new FormData();
    form.set("kind", kind);
    if (file) form.set("file", file);
    else form.set("text", text);
    return request<Doc>(`${ws}/documents`, { form, auth: authOf() });
  };

  const post = <T,>(path: string, json: object) => request<T>(`${ws}${path}`, { json, auth: authOf() });

  const ensureDocs = async () => {
    let { r, j } = docs;
    setStage("Uploading your documents");
    if (!r) r = await upload("resume", resumeText, resumeFile);
    if (!j) j = await upload("job_description", jdText, jdFile);
    setDocs({ r, j });
    return { r, j };
  };

  const analyse = async () => {
    setError(null);
    setReport(null);
    try {
      const { r, j } = await ensureDocs();
      setStage("Analysing your resume");
      const resume = await post<{ analysis: Resume }>("/resume/analyze", { document_id: r.document_id });
      setStage("Analysing the job description");
      const jd = await post<{ analysis: Jd }>("/job-description/analyze", { document_id: j.document_id });
      const pair = { resume_document_id: r.document_id, job_description_document_id: j.document_id };
      setStage("Calculating your match");
      const match = await post<{ match: Match; report_id?: string | null }>("/career/match", { ...pair, ...(wantReport ? { report_format: "pdf" } : {}) });
      setStage("Finding skill gaps");
      const gap = await post<{ analysis: GapAnalysis }>("/career/skill-gap", pair);
      setRes({ resume: resume.analysis, jd: jd.analysis, match: match.match, gap: gap.analysis });
      setReport(match.report_id ?? null);
      setTimeout(() => document.getElementById("results")?.scrollIntoView?.({ behavior: "smooth" }), 50);
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setStage(null);
    }
  };

  const optimise = async () => {
    if (!docs.r || !docs.j) return;
    setOptBusy(true);
    setError(null);
    try {
      const out = await post<{ result: Optim }>("/resume/optimize", {
        resume_document_id: docs.r.document_id, job_description_document_id: docs.j.document_id, approved_change_ids: approved,
      });
      setRes((o) => ({ ...o, opt: out.result }));
    } catch (e) {
      setError(messageOf(e));
    } finally {
      setOptBusy(false);
    }
  };

  const m = res.match;
  const flagged = docs.r?.injection_flagged || docs.j?.injection_flagged;

  return (
    <>
      <PageHeader
        title="Resume and job analysis"
        subtitle="Paste or upload your resume and a target job description. One click gives you the match score, your skill gaps and a full analysis of both documents."
      />
      {guest && (
        <Notice tone="info">
          You are in a temporary guest session: nothing is saved to an account and your documents are deleted when the
          session expires. <Link className="font-medium underline" to="/register">Register</Link> to keep your history.
        </Notice>
      )}
      <ErrorBox error={error} />

      <div className="grid gap-5 md:grid-cols-2">
        <DocInput id="resume-input" title="Resume" icon="📄" hint="Your resume as text, or upload a file."
          text={resumeText} setText={(v) => { setResumeText(v); forget(); }} file={resumeFile}
          setFile={(f) => { setResumeFile(f); forget(); }} sample={SAMPLE_RESUME} />
        <DocInput id="jd-input" title="Job description" icon="💼" hint="The role you want to match against."
          text={jdText} setText={(v) => { setJdText(v); forget(); }} file={jdFile}
          setFile={(f) => { setJdFile(f); forget(); }} sample={SAMPLE_JD} />
      </div>

      <div className="mt-5 flex flex-col items-center gap-3 rounded-2xl border border-indigo-100 bg-indigo-50/60 p-5">
        <Button className="px-8 py-3 text-base" busy={busy} disabled={!hasResume || !hasJd} onClick={analyse}>
          🎯 Analyse and match
        </Button>
        {busy ? (
          <p role="status" className="text-sm text-indigo-700">{stage}…</p>
        ) : (
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input type="checkbox" checked={wantReport} onChange={(e) => setWantReport(e.target.checked)} />
            Also create a downloadable PDF report
          </label>
        )}
        {!hasResume || !hasJd ? <p className="text-xs text-slate-500">Add both a resume and a job description to continue.</p> : null}
      </div>

      {flagged && (
        <div className="mt-4">
          <Notice>A document contained text that looks like instructions to an AI. It was treated as plain data and ignored.</Notice>
        </div>
      )}

      <div id="results" className="mt-8 scroll-mt-4">
        {!m && !busy && <Empty>Your results will appear here: match score, skill gaps, resume and job analysis.</Empty>}

        {m && (
          <>
            <nav aria-label="Result sections" className="mb-4 flex flex-wrap gap-2 text-sm">
              {[["match", "Match"], ["gaps", "Skill gaps"], ["resume", "Resume analysis"], ["jd", "Job analysis"], ["optimise", "Optimise"]].map(([id, label]) => (
                <a key={id} href={`#${id}`} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-slate-600 hover:border-indigo-300 hover:text-indigo-700"
                  onClick={(e) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView?.({ behavior: "smooth" }); }}>{label}</a>
              ))}
              {report && (
                <button className="rounded-full bg-indigo-600 px-3 py-1 text-white"
                  onClick={() => download(`${ws}/reports/${report}/download`, "report.pdf", { auth: authOf() }).catch((e) => setError(messageOf(e)))}>
                  ⬇ Download PDF report
                </button>
              )}
            </nav>

            <section id="match" className="scroll-mt-4">
              <Card title="Match estimate" subtitle="How well your resume fits this job, broken down by category" icon="🎯">
                <div className="flex flex-col gap-6 md:flex-row">
                  <ScoreRing value={m.overall_score} label="match" />
                  <div className="flex-1">
                    {m.category_scores.map((c) => <Bar key={c.category} label={c.category} value={c.score} detail={`${c.detail} · weight ${c.weight}`} />)}
                  </div>
                </div>
                {m.disclaimer && <p className="mt-3 text-xs text-slate-500">{m.disclaimer}</p>}
                <div className="mt-4 grid gap-4 md:grid-cols-3">
                  <div><h3 className="mb-1 text-sm font-semibold text-emerald-700">✔ Matching ({m.matching_skills.length})</h3><Chips tone="green" items={m.matching_skills.map((s) => s.skill)} /></div>
                  <div><h3 className="mb-1 text-sm font-semibold text-amber-700">◐ Partial ({m.partial_skills.length})</h3>
                    <Chips tone="amber" items={m.partial_skills.map((s) => `${s.skill} (you show ${s.related_resume_skill ?? "related skills"})`)} /></div>
                  <div><h3 className="mb-1 text-sm font-semibold text-red-700">✘ Missing ({m.missing_skills.length})</h3>
                    <Chips tone="red" items={m.missing_skills.map((s) => `${s.skill} (${s.level})`)} /></div>
                </div>
                {m.recommendations.length > 0 && (<><h3 className="mb-1 mt-4 text-sm font-semibold">Recommendations</h3><List items={m.recommendations} /></>)}
              </Card>
            </section>

            {res.gap && (
              <section id="gaps" className="scroll-mt-4">
                <Card title="Skill gap analysis" subtitle={res.gap.summary} icon="🧭">
                  {res.gap.gaps.length === 0 && <Empty>No gaps found for this job.</Empty>}
                  <div className="grid gap-3 md:grid-cols-2">
                    {res.gap.gaps.map((g) => (
                      <article key={g.skill} className="rounded-xl border border-slate-200 p-4">
                        <div className="mb-2 flex flex-wrap items-center gap-2">
                          <h3 className="font-semibold capitalize">{g.skill}</h3>
                          <Chip tone={sevTone(g.severity)}>{g.severity}</Chip>
                          <Chip>{g.status.replace(/_/g, " ")}</Chip>
                          <span className="ml-auto text-xs text-slate-500">≈ {g.suggested_timeline_days} days</span>
                        </div>
                        <p className="mb-2 text-sm text-slate-600">{g.current_evidence}</p>
                        {g.learning_recommendations.length > 0 && <List items={g.learning_recommendations} />}
                        {g.practical_exercises && g.practical_exercises.length > 0 && (
                          <p className="mt-2 text-xs text-slate-500"><b>Practise:</b> {g.practical_exercises.join(" · ")}</p>
                        )}
                      </article>
                    ))}
                  </div>
                  {res.gap.note && <p className="mt-3 text-xs text-slate-500">{res.gap.note}</p>}
                  <div className="mt-4">
                    <Link to={user ? "/learning" : "/register"} className="inline-block rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">
                      {user ? "Build a learning roadmap (7, 15 or 60 days)" : "Register to build a 7, 15 or 60 day roadmap"}
                    </Link>
                  </div>
                </Card>
              </section>
            )}

            {res.resume && (
              <section id="resume" className="scroll-mt-4">
                <Card title="Resume analysis" subtitle={res.resume.experience_summary} icon="📄">
                  <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-4">
                    <Stat label="Resume quality" value={`${res.resume.quality.score}/100`} hint="heuristic" />
                    <Stat label="Skills found" value={res.resume.technical_skills.length} />
                    <Stat label="Strengths" value={res.resume.strengths.length} />
                    <Stat label="To improve" value={res.resume.weaknesses.length} />
                  </div>
                  <p className="mb-3 text-xs text-slate-500">{res.resume.quality.note}</p>
                  <h3 className="mb-1 text-sm font-semibold">Skills found</h3>
                  <div className="mb-4"><Chips tone="indigo" items={res.resume.technical_skills.map((s) => s.skill)} empty="None detected" /></div>
                  <div className="grid gap-4 md:grid-cols-3">
                    <div><h3 className="mb-1 text-sm font-semibold text-emerald-700">Strengths</h3><List items={res.resume.strengths} /></div>
                    <div><h3 className="mb-1 text-sm font-semibold text-amber-700">Weaknesses</h3><List items={res.resume.weaknesses} /></div>
                    <div><h3 className="mb-1 text-sm font-semibold text-sky-700">ATS recommendations</h3><List items={res.resume.ats_recommendations} /></div>
                  </div>
                </Card>
              </section>
            )}

            {res.jd && (
              <section id="jd" className="scroll-mt-4">
                <Card title={`Job description: ${res.jd.title ?? "untitled role"}`} subtitle="What the employer asks for" icon="💼">
                  <div className="grid gap-4 md:grid-cols-3">
                    <div><h3 className="mb-1 text-sm font-semibold text-red-700">Mandatory</h3><Chips tone="red" items={res.jd.mandatory_skills} /></div>
                    <div><h3 className="mb-1 text-sm font-semibold text-amber-700">Preferred</h3><Chips tone="amber" items={res.jd.preferred_skills} /></div>
                    <div><h3 className="mb-1 text-sm font-semibold text-slate-700">Optional</h3><Chips items={res.jd.optional_skills} /></div>
                  </div>
                  <h3 className="mb-1 mt-4 text-sm font-semibold">Responsibilities</h3>
                  <List items={res.jd.responsibilities} />
                </Card>
              </section>
            )}

            <section id="optimise" className="scroll-mt-4">
              <Card title="Optimise your resume for this job" subtitle="Rewrites wording and keywords. It never adds skills or experience you did not state; larger changes need your approval." icon="✍️">
                <Button variant={res.opt ? "secondary" : "primary"} busy={optBusy} onClick={optimise}>
                  {res.opt ? "Run again with my approvals" : "Optimise my resume"}
                </Button>
                {res.opt && (
                  <div className="mt-4">
                    {res.opt.note && <Notice tone="info">{res.opt.note}</Notice>}
                    {res.opt.clarification_questions.length > 0 && (<><h3 className="mb-1 text-sm font-semibold">Questions for you</h3><List items={res.opt.clarification_questions} /></>)}
                    <h3 className="mb-2 mt-3 text-sm font-semibold">Changes</h3>
                    {res.opt.changes.map((c) => (
                      <div key={c.id} className="mb-2 rounded-xl border border-slate-200 p-3 text-sm">
                        <div className="mb-1 flex flex-wrap items-center gap-2">
                          <b className="capitalize">{c.section}</b><Chip tone="indigo">{c.change_type}</Chip>
                          <Chip tone={c.applied ? "green" : "amber"}>{c.applied ? "applied" : "needs your approval"}</Chip>
                        </div>
                        <p className="text-slate-500">Before: {c.before || "(empty)"}</p>
                        <p>After: {c.after}</p>
                        <p className="text-xs text-slate-500">{c.reason}</p>
                        {!c.applied && (
                          <label className="mt-1 flex items-center gap-2">
                            <input type="checkbox" checked={approved.includes(c.id)}
                              onChange={(e) => setApproved((a) => (e.target.checked ? [...a, c.id] : a.filter((x) => x !== c.id)))} />
                            Approve this change, then run again
                          </label>
                        )}
                      </div>
                    ))}
                    <h3 className="mb-1 mt-3 text-sm font-semibold">Resulting text</h3>
                    <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-xl bg-slate-100 p-3 text-sm">{res.opt.optimized_resume_text}</pre>
                  </div>
                )}
              </Card>
            </section>
          </>
        )}
      </div>
    </>
  );
}
