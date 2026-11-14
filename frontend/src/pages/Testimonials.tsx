import { FormEvent, useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { API_ROOT, messageOf, request } from "../api/http";
import { Button, Card, ErrorBox, Field, Notice, Spinner, inputCls } from "../components/ui";
import { FEEDBACK_FEATURES, PLATFORM_LABEL, SHARE_PLATFORMS, type SharePlatform } from "../lib/constants";
import { useSession } from "../store/session";

interface PublicT { id: string; text: string; display_name: string; rating: number | null; success_story: string | null; feature: string }
interface Mine {
  id: string; text: string; status: string; is_public: boolean; public_consent: boolean;
  consent_withdrawn_at: string | null; rating: number | null; display_name: string | null;
}
interface Share { public_url: string; share_text: string; links: Record<SharePlatform, string>; note: string }

const stars = (n: number | null) => (n ? "★".repeat(n) + "☆".repeat(5 - n) : "");
const cardUrl = (id: string) => `${API_ROOT}/testimonials/public/${id}/card.png`;
const record = (id: string, event_type: string, platform?: SharePlatform) =>
  request(`/testimonials/public/${id}/events`, { json: { event_type, platform }, auth: "none" }).catch(() => undefined);

/** Share *interfaces* only: each link opens the platform's own dialog; nothing is posted for the user. */
export function ShareButtons({ id }: { id: string }) {
  const q = useQuery({ queryKey: ["share", id], retry: false, queryFn: () => request<Share>(`/testimonials/${id}/share`) });
  const [copied, setCopied] = useState<string | null>(null);
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <p className="text-xs text-gray-500">{messageOf(q.error)}</p>;
  const s = q.data;
  const copy = async (what: "link" | "text") => {
    await navigator.clipboard?.writeText(what === "link" ? s.public_url : `${s.share_text} ${s.public_url}`);
    setCopied(what);
    void record(id, "link_copy");
  };
  return (
    <div className="mt-2 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        {SHARE_PLATFORMS.map((p) => (
          <a key={p} href={s.links[p]} target="_blank" rel="noopener noreferrer"
            className="rounded border px-2 py-1 text-blue-700" onClick={() => void record(id, "share_click", p)}>
            Share on {PLATFORM_LABEL[p]}
          </a>
        ))}
        <button className="rounded border px-2 py-1" onClick={() => void copy("link")}>Copy link</button>
        <button className="rounded border px-2 py-1" onClick={() => void copy("text")}>Copy text</button>
        {typeof navigator !== "undefined" && "share" in navigator && (
          <button className="rounded border px-2 py-1" onClick={() => void navigator.share({ text: s.share_text, url: s.public_url })}>More…</button>
        )}
        <a className="rounded border px-2 py-1" href={cardUrl(id)} download="testimonial.png" onClick={() => void record(id, "card_download")}>
          Download card (PNG)
        </a>
      </div>
      {copied && <p role="status" className="mt-1 text-xs">Copied {copied}.</p>}
      <p className="mt-1 text-xs text-gray-500">{s.note}</p>
    </div>
  );
}

export function PublicTestimonials() {
  const user = useSession((s) => s.user);
  const q = useQuery({ queryKey: ["pubt"], queryFn: () => request<PublicT[]>("/testimonials/public", { auth: "none" }) });
  return (
    <>
      <h1 className="mb-2 text-2xl font-bold">What learners say</h1>
      <p className="mb-3 text-sm text-gray-700">
        Only testimonials that the author agreed to publish and that a moderator approved appear here.
      </p>
      {q.isLoading && <Spinner />}
      <ErrorBox error={q.error ? messageOf(q.error) : null} />
      {q.data?.length === 0 && <p className="text-sm text-gray-500">No testimonials have been published yet.</p>}
      <div className="grid gap-3 md:grid-cols-2">
        {q.data?.map((t) => (
          <Card key={t.id}>
            <p aria-label={t.rating ? `${t.rating} out of 5` : undefined} className="text-amber-500">{stars(t.rating)}</p>
            <blockquote className="text-sm">“{t.text}”</blockquote>
            {t.success_story && <p className="mt-1 text-sm text-gray-700">{t.success_story}</p>}
            <p className="mt-2 text-sm font-medium">— {t.display_name}</p>
          </Card>
        ))}
      </div>
      {user && <p className="mt-4 text-sm"><a className="text-blue-700 underline" href="/feedback">Share your own experience</a></p>}
    </>
  );
}

export function Feedback() {
  const qc = useQueryClient();
  const [feature, setFeature] = useState("platform");
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [text, setText] = useState("");
  const [story, setStory] = useState("");
  const [name, setName] = useState("");
  const [consent, setConsent] = useState(false); // never pre-ticked
  const [sent, setSent] = useState<string | null>(null);

  const mine = useQuery({ queryKey: ["mine"], queryFn: () => request<Mine[]>("/testimonials") });
  const rate = useMutation({
    mutationFn: () => request("/feedback", { json: { feature, rating, comment: comment || undefined } }),
    onSuccess: () => { setSent("Thank you for your rating."); setComment(""); },
  });
  const create = useMutation({
    mutationFn: () => request<Mine>("/testimonials", { json: { text, feature, rating, success_story: story || undefined, display_name: name || undefined, public_consent: consent } }),
    onSuccess: () => { setText(""); setStory(""); setConsent(false); void qc.invalidateQueries({ queryKey: ["mine"] }); },
  });
  const withdraw = useMutation({
    mutationFn: (id: string) => request(`/testimonials/${id}/withdraw-consent`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mine"] }),
  });
  const del = useMutation({
    mutationFn: (id: string) => request(`/testimonials/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mine"] }),
  });
  const submitRating = (e: FormEvent) => { e.preventDefault(); rate.mutate(); };
  const submitT = (e: FormEvent) => { e.preventDefault(); create.mutate(); };
  const err = rate.error ?? create.error ?? withdraw.error ?? del.error;

  return (
    <>
      <h1 className="mb-3 text-2xl font-bold">Feedback and testimonials</h1>
      <ErrorBox error={err ? messageOf(err) : null} />
      <Card title="Rate a feature">
        <form onSubmit={submitRating}>
          <Field label="Feature">
            <select className={inputCls} value={feature} onChange={(e) => setFeature(e.target.value)}>
              {Object.entries(FEEDBACK_FEATURES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <Field label="Rating (1 to 5)">
            <select className={inputCls} value={rating} onChange={(e) => setRating(Number(e.target.value))}>
              {[5, 4, 3, 2, 1].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </Field>
          <Field label="Comment (optional, private)">
            <textarea className={inputCls} rows={2} maxLength={1000} value={comment} onChange={(e) => setComment(e.target.value)} />
          </Field>
          <Button type="submit" busy={rate.isPending}>Submit rating</Button>
          {sent && <span role="status" className="ml-3 text-sm">{sent}</span>}
        </form>
      </Card>
      <Card title="Write a testimonial">
        <form onSubmit={submitT}>
          <Field label="Your testimonial (20 to 1000 characters). Review it before sending; you can edit or delete it later.">
            <textarea className={inputCls} rows={4} minLength={20} maxLength={1000} required value={text} onChange={(e) => setText(e.target.value)} />
          </Field>
          <Field label="Success story (optional)">
            <textarea className={inputCls} rows={2} maxLength={2000} value={story} onChange={(e) => setStory(e.target.value)} />
          </Field>
          <Field label="Name to show publicly (optional; leave blank to appear as Anonymous learner)">
            <input className={inputCls} maxLength={60} value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <label className="mb-3 flex items-start gap-2 text-sm">
            <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
            I agree that this testimonial may be shown publicly, and shared, if a moderator approves it. I can withdraw this at any time.
          </label>
          <Button type="submit" busy={create.isPending}>Submit testimonial</Button>
        </form>
      </Card>
      <Card title="Your testimonials">
        {mine.data?.length === 0 && <p className="text-sm text-gray-500">None yet.</p>}
        {mine.data?.map((t) => (
          <div key={t.id} className="border-t py-2 text-sm">
            <p>“{t.text}”</p>
            <p className="text-xs text-gray-600">
              Status: {t.status} · {t.is_public ? "public" : t.public_consent ? "waiting for approval" : "not shared publicly"}
              {t.consent_withdrawn_at ? " · consent withdrawn" : ""}
            </p>
            {!t.public_consent && !t.consent_withdrawn_at && <Notice>Not published: you did not agree to public display.</Notice>}
            {t.is_public && <ShareButtons id={t.id} />}
            <div className="mt-1 flex gap-3">
              {t.public_consent && <button className="text-blue-700 underline" onClick={() => withdraw.mutate(t.id)}>Withdraw public consent</button>}
              <button className="text-red-700 underline" onClick={() => del.mutate(t.id)}>Delete</button>
            </div>
          </div>
        ))}
      </Card>
    </>
  );
}

/** Target of the shared public URL. Anything not approved and consented is shown as not available. */
export function PublicTestimonialPage() {
  const { id = "" } = useParams();
  const q = useQuery({ queryKey: ["pubt1", id], retry: false, queryFn: () => request<PublicT>(`/testimonials/public/${encodeURIComponent(id)}`, { auth: "none" }) });
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <p role="alert">This testimonial is not available.</p>;
  return (
    <Card>
      <p className="text-amber-500">{stars(q.data.rating)}</p>
      <blockquote className="text-sm">“{q.data.text}”</blockquote>
      <p className="mt-2 text-sm font-medium">— {q.data.display_name}</p>
    </Card>
  );
}
