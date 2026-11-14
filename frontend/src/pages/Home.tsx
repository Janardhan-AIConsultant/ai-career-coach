import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { request } from "../api/http";
import { useSession } from "../store/session";

const SERVICES = [
  ["📄", "Resume analysis", "Skills, strengths, weaknesses and ATS advice, extracted from your resume."],
  ["💼", "Job description analysis", "Mandatory, preferred and optional requirements, separated for you."],
  ["🎯", "Resume and job match", "A transparent, explainable match score with a category breakdown."],
  ["🧭", "Skill gap analysis", "What is missing, how severe it is, and a realistic study timeline."],
  ["✍️", "Resume optimisation", "Sharper wording and keywords. It never invents skills or experience."],
  ["🎤", "Interview practice", "Questions tailored to your gaps, with model answers and feedback."],
];

const ACCOUNT = [
  ["🗓️", "Learning roadmaps", "Structured plans of 7, 15 or 60 days built around your gaps."],
  ["📝", "Assessments", "Server-scored quizzes. Passing one completes the matching roadmap step."],
  ["🏅", "Certificates", "Issued from your verified records, with a public verification page."],
  ["📁", "Career portfolio", "Private by default; publish only what you choose, with your consent."],
  ["🤖", "AI Career Coach", "Answers grounded in your own documents, never invented facts."],
  ["💬", "Testimonials", "Share your experience on LinkedIn, WhatsApp or Facebook, only if you want to."],
];

const STEPS = [
  ["1", "Add your documents", "Paste or upload a resume and a job description."],
  ["2", "Get your results", "Match score, skill gaps and a full analysis, side by side."],
  ["3", "Close the gaps", "Register for a 7, 15 or 60 day roadmap with assessments."],
  ["4", "Show your progress", "Earn certificates and share a consent-based portfolio."],
];

interface PublicT { id: string; text: string; display_name: string; rating: number | null; success_story: string | null }
interface Stats { ratings_count: number; average_rating: number | null; testimonials_count: number }
const stars = (n: number) => "★".repeat(n) + "☆".repeat(5 - n);

const ROTATE_MS = 5000;
const prefersReducedMotion = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Real, approved and consented testimonials only, shown one at a time and rotated automatically.
 *  Nothing is shown (and nothing invented) when there are none. Rotation pauses on hover/focus and via a button,
 *  and never starts when the visitor prefers reduced motion. */
function Testimonials() {
  const q = useQuery({ queryKey: ["home-testimonials"], queryFn: () => request<PublicT[]>("/testimonials/public", { auth: "none", query: { limit: 6 } }) });
  const stats = useQuery({ queryKey: ["home-stats"], queryFn: () => request<Stats>("/feedback/stats", { auth: "none" }) });
  const items = q.data ?? [];
  const [index, setIndex] = useState(0);
  const [hover, setHover] = useState(false);
  const [userPaused, setUserPaused] = useState(false);
  const reduced = prefersReducedMotion();
  const paused = hover || userPaused || reduced;
  useEffect(() => {
    if (items.length < 2 || paused) return;
    const id = setInterval(() => setIndex((n) => (n + 1) % items.length), ROTATE_MS);
    return () => clearInterval(id);
  }, [items.length, paused]);
  if (q.isError) return null; // the landing page must never break because of this section
  const avg = stats.data?.average_rating;
  const pos = items.length ? index % items.length : 0;
  const current = items[pos];
  return (
    <section aria-labelledby="stories" aria-roledescription="carousel" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)} onBlur={() => setHover(false)}
      className="flex h-full flex-col rounded-3xl bg-gradient-to-br from-amber-50 to-orange-50 p-6 md:p-8">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="stories" className="text-xl font-bold">Learners like you are moving forward</h2>
          <p className="text-sm text-slate-600">
            {items.length > 0 && items.every((t) => /\((sample|demo)\)/i.test(t.display_name))
              ? "Sample testimonials for preview. Real ones replace them as learners choose to publish."
              : "Real words from people who used the platform, shown with their permission."}
          </p>
        </div>
        {avg != null && stats.data && stats.data.ratings_count > 0 && (
          <p className="rounded-xl bg-white px-4 py-2 text-sm shadow-sm" aria-label={`Average rating ${avg} out of 5`}>
            <span className="text-lg font-bold text-amber-500">{"★"} {avg.toFixed(1)}</span>
            <span className="text-slate-500"> average from {stats.data.ratings_count} rating{stats.data.ratings_count === 1 ? "" : "s"}</span>
          </p>
        )}
      </div>
      {!current ? (
        <p className="rounded-xl border border-dashed border-amber-300 bg-white/70 p-5 text-center text-sm text-slate-600">
          No testimonials have been published yet. Finish your first analysis or roadmap and be the first to share how it went.
        </p>
      ) : (
        <>
          <figure key={current.id} aria-live="off" className="fade-in flex min-h-[11rem] flex-1 flex-col justify-between rounded-2xl border border-amber-100 bg-white p-6 shadow-sm">
            <div>
              {current.rating ? <p aria-label={`${current.rating} out of 5`} className="mb-2 text-lg text-amber-500">{stars(current.rating)}</p> : null}
              <blockquote className="text-base leading-relaxed text-slate-700">&ldquo;{current.text}&rdquo;</blockquote>
              {current.success_story && <p className="mt-2 text-xs text-slate-500">{current.success_story}</p>}
            </div>
            <figcaption className="mt-4 text-sm font-semibold text-slate-900">&mdash; {current.display_name}</figcaption>
          </figure>
          {items.length > 1 && (
            <div className="mt-3 flex items-center gap-3">
              <div className="flex gap-2" role="group" aria-label="Choose a testimonial">
                {items.map((t, i) => (
                  <button key={t.id} type="button" onClick={() => setIndex(i)} aria-label={`Show testimonial ${i + 1} of ${items.length}`}
                    aria-current={i === pos ? "true" : undefined}
                    className={`h-2.5 rounded-full transition-all ${i === pos ? "w-6 bg-indigo-600" : "w-2.5 bg-amber-300 hover:bg-amber-400"}`} />
                ))}
              </div>
              {!reduced && (
                <button type="button" onClick={() => setUserPaused((v) => !v)} className="ml-auto text-xs font-medium text-slate-600 underline">
                  {userPaused ? "Resume rotation" : "Pause rotation"}
                </button>
              )}
            </div>
          )}
        </>
      )}
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Link to="/analyze" className="rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700">Start your own journey</Link>
        {items.length > 0 && <Link to="/testimonials" className="text-sm font-medium text-indigo-700 underline">Read more stories</Link>}
      </div>
    </section>
  );
}

function IntroVideo() {
  return (
    <section aria-labelledby="intro-video" className="flex h-full flex-col rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200 md:p-8">
      <p className="text-xs font-semibold uppercase tracking-widest text-indigo-600">Watch · 30 seconds</p>
      <h2 id="intro-video" className="mt-1 text-xl font-bold text-slate-900">See how AI Career Coach works</h2>
      <p className="mt-1 text-sm text-slate-600">From resume match to roadmap, practice and certificates. A quick tour from your guide.</p>
      <div className="mt-4 overflow-hidden rounded-2xl bg-slate-900 shadow-lg">
        <video controls preload="metadata" playsInline poster="/video/ai-career-coach-intro-poster.jpg" className="aspect-video w-full"
          aria-label="AI Career Coach introduction video">
          <source src="/video/ai-career-coach-intro-1080p.mp4" type="video/mp4" />
          <track kind="captions" src="/video/ai-career-coach-intro.vtt" srcLang="en" label="English" default />
          Your browser cannot play this video. <a href="/video/ai-career-coach-intro-1080p.mp4">Download it instead</a>.
        </video>
      </div>
      <a className="mt-3 inline-block text-sm font-medium text-indigo-700 underline" href="/video/ai-career-coach-intro-4k.mp4" download>
        Download the 4K version
      </a>
    </section>
  );
}

export default function Home() {
  const user = useSession((s) => s.user);
  return (
    <>
      <section className="mb-10 overflow-hidden rounded-3xl bg-gradient-to-br from-indigo-700 via-indigo-600 to-sky-500 p-8 text-white shadow-lg md:p-12">
        <p className="mb-2 inline-block rounded-full bg-white/15 px-3 py-1 text-xs font-medium">No sign-in needed to try it</p>
        <h1 className="max-w-3xl text-3xl font-extrabold leading-tight md:text-5xl">Know exactly how you match a job, and how to close the gap.</h1>
        <p className="mt-4 max-w-2xl text-lg text-indigo-50">
          Upload your resume and a job description. Get an explainable match score, your skill gaps, and an
          optimised resume. Every number comes from transparent rules, not a guess from a language model.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link to="/analyze" className="rounded-xl bg-white px-5 py-3 font-semibold text-indigo-700 shadow hover:bg-indigo-50">Analyse my resume</Link>
          {!user && <Link to="/register" className="rounded-xl border border-white/60 px-5 py-3 font-semibold text-white hover:bg-white/10">Create a free account</Link>}
          {user && <Link to="/learning" className="rounded-xl border border-white/60 px-5 py-3 font-semibold text-white hover:bg-white/10">Go to my learning</Link>}
        </div>
      </section>

      <div className="mb-10 grid items-stretch gap-6 lg:grid-cols-2">
        <Testimonials />
        <IntroVideo />
      </div>

      <h2 className="mb-1 text-xl font-bold">Try it right now, no account</h2>
      <p className="mb-4 text-sm text-slate-600">Guest sessions are temporary and their documents are deleted when they expire.</p>
      <div className="mb-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SERVICES.map(([icon, t, d], i) => (
          <article key={t} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md">
            <span aria-hidden className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-50 text-xl">{icon}</span>
            <h3 className="font-semibold">{t}</h3>
            <p className="mt-1 text-sm text-slate-600">{d}</p>
            {i === 5 && <p className="mt-2 text-xs text-slate-400">Requires an account</p>}
          </article>
        ))}
      </div>

      <h2 className="mb-1 text-xl font-bold">With a free account</h2>
      <p className="mb-4 text-sm text-slate-600">Keep your history and turn insights into a plan.</p>
      <div className="mb-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ACCOUNT.map(([icon, t, d]) => (
          <article key={t} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <span aria-hidden className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-xl">{icon}</span>
            <h3 className="font-semibold">{t}</h3>
            <p className="mt-1 text-sm text-slate-600">{d}</p>
          </article>
        ))}
      </div>

      <h2 className="mb-4 text-xl font-bold">How it works</h2>
      <ol className="mb-6 grid gap-4 md:grid-cols-4">
        {STEPS.map(([n, t, d]) => (
          <li key={n} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <span className="mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-sm font-bold text-white">{n}</span>
            <h3 className="font-semibold">{t}</h3>
            <p className="mt-1 text-sm text-slate-600">{d}</p>
          </li>
        ))}
      </ol>
    </>
  );
}
