import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { download, messageOf, request } from "../api/http";
import { Button, Card, ErrorBox, List, Spinner, inputCls, PageHeader } from "../components/ui";

interface Overview {
  users: { total: number; active: number; admins: number; new_7d: number; new_30d: number };
  guests: { active_sessions: number; expired_pending_cleanup: number };
  learning: { assessment_attempts: number; assessment_pass_rate: number | null; roadmaps_by_duration: Record<string, number> };
  achievements: { certificates_by_status: Record<string, number>; public_portfolios: number };
  community: { ratings: number; average_rating: number | null; testimonials_by_status: Record<string, number> };
}
interface AdminT { id: string; text: string; display_name: string | null; status: string; public_consent: boolean; review_hints: string[] }
interface AdminU { id: string; email: string; display_name: string; role: string; is_active: boolean }
interface Sys { environment: string; components: { name: string; status: string; detail: string }[]; warnings: string[] }

const Stat = ({ label, value }: { label: string; value: string | number }) => (
  <div className="rounded border bg-white p-3 text-center">
    <div className="text-2xl font-bold">{value}</div>
    <div className="text-xs text-gray-600">{label}</div>
  </div>
);

export function AdminHome() {
  const qc = useQueryClient();
  const ov = useQuery({ queryKey: ["a-ov"], queryFn: () => request<Overview>("/admin/overview") });
  const sys = useQuery({ queryKey: ["a-sys"], queryFn: () => request<Sys>("/admin/system") });
  const [filter, setFilter] = useState("pending");
  const queue = useQuery({ queryKey: ["a-q", filter], queryFn: () => request<AdminT[]>("/admin/testimonials", { query: { status: filter } }) });
  const [search, setSearch] = useState("");
  const users = useQuery({ queryKey: ["a-u", search], queryFn: () => request<AdminU[]>("/admin/users", { query: { search } }) });
  const moderate = useMutation({
    mutationFn: (v: { id: string; action: string }) => request(`/admin/testimonials/${v.id}/moderate`, { json: { action: v.action } }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["a-q"] }); void qc.invalidateQueries({ queryKey: ["a-ov"] }); },
  });
  const patch = useMutation({
    mutationFn: (v: { id: string; is_active: boolean }) => request(`/admin/users/${v.id}`, { method: "PATCH", json: { is_active: v.is_active } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["a-u"] }),
  });
  const err = ov.error ?? moderate.error ?? patch.error;
  const o = ov.data;

  return (
    <>
      <PageHeader title="Administration" />
      <ErrorBox error={err ? messageOf(err) : null} />
      {ov.isLoading && <Spinner />}
      {o && (
        <div className="mb-4 grid grid-cols-2 gap-2 md:grid-cols-4">
          <Stat label="Users" value={o.users.total} />
          <Stat label="New (7 days)" value={o.users.new_7d} />
          <Stat label="Active guest sessions" value={o.guests.active_sessions} />
          <Stat label="Assessment pass rate" value={o.learning.assessment_pass_rate === null ? "n/a" : `${o.learning.assessment_pass_rate}%`} />
          <Stat label="Ratings" value={o.community.ratings} />
          <Stat label="Average rating" value={o.community.average_rating ?? "n/a"} />
          <Stat label="Public portfolios" value={o.achievements.public_portfolios} />
          <Stat label="Pending testimonials" value={o.community.testimonials_by_status.pending ?? 0} />
        </div>
      )}
      <Card title="Testimonial moderation">
        <select aria-label="Status filter" className={`${inputCls} mb-2 max-w-xs`} value={filter} onChange={(e) => setFilter(e.target.value)}>
          {["pending", "approved", "flagged", "rejected", "removed"].map((s) => <option key={s}>{s}</option>)}
        </select>
        {queue.data?.length === 0 && <p className="text-sm text-gray-500">Nothing in this queue.</p>}
        {queue.data?.map((t) => (
          <div key={t.id} className="border-t py-2 text-sm">
            <p>“{t.text}”</p>
            <p className="text-xs text-gray-600">{t.display_name ?? "Anonymous"} · {t.status}</p>
            {t.review_hints.length > 0 && <List items={t.review_hints} />}
            <div className="mt-1 flex gap-2">
              {["approve", "reject", "flag", "remove"].map((a) => (
                <button key={a} className="rounded border px-2 py-0.5" disabled={moderate.isPending} onClick={() => moderate.mutate({ id: t.id, action: a })}>{a}</button>
              ))}
            </div>
          </div>
        ))}
      </Card>
      <Card title="Users">
        <input className={`${inputCls} mb-2 max-w-xs`} aria-label="Search users" placeholder="Search by name or email" value={search} onChange={(e) => setSearch(e.target.value)} />
        {users.data?.map((u) => (
          <div key={u.id} className="flex items-center justify-between border-t py-1 text-sm">
            <span>{u.display_name} ({u.email}) · {u.role} · {u.is_active ? "active" : "deactivated"}</span>
            <button className="text-blue-700 underline" onClick={() => patch.mutate({ id: u.id, is_active: !u.is_active })}>
              {u.is_active ? "Deactivate" : "Reactivate"}
            </button>
          </div>
        ))}
      </Card>
      <Card title="System">
        {sys.data && (
          <>
            <p className="text-sm">Environment: {sys.data.environment}</p>
            <ul className="text-sm">{sys.data.components.map((c) => <li key={c.name}>{c.name}: {c.status} ({c.detail})</li>)}</ul>
            <List items={sys.data.warnings} empty="No warnings" />
          </>
        )}
        <button className="mt-2 text-sm text-blue-700 underline" onClick={() => download("/admin/feedback/export.csv", "feedback-aggregate.csv")}>
          Export aggregate feedback (CSV)
        </button>
      </Card>
    </>
  );
}
