import { FormEvent, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { messageOf, request } from "../api/http";
import { Button, Card, ErrorBox, Field, Spinner, inputCls } from "../components/ui";
import { ROADMAP_DURATIONS } from "../lib/constants";

interface Summary { id: string; title: string; duration_days: number; status: string; percent_required_complete: number }
interface Activity {
  id: string; day_number: number; title: string; kind: string; description: string | null;
  estimated_minutes: number | null; is_required: boolean; completed_at: string | null;
}
interface Module { id: string; position: number; title: string; objectives: string[]; activities: Activity[]; completed: number; total: number }
interface Roadmap extends Summary {
  goal: string; estimated_hours: number | null; modules: Module[];
  progress: { percent_required_complete: number; criteria_met: boolean; requirements: { name: string; met: boolean }[] };
}

export function LearningList() {
  const qc = useQueryClient();
  const [goal, setGoal] = useState("");
  const [days, setDays] = useState<number>(ROADMAP_DURATIONS[0]);
  const list = useQuery({ queryKey: ["roadmaps"], queryFn: () => request<Summary[]>("/learning/roadmaps") });
  const create = useMutation({
    mutationFn: () => request<Roadmap>("/learning/roadmaps", { json: { duration_days: days, goal } }),
    onSuccess: () => { setGoal(""); void qc.invalidateQueries({ queryKey: ["roadmaps"] }); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); create.mutate(); };

  return (
    <>
      <h1 className="mb-3 text-2xl font-bold">Learning roadmaps</h1>
      <Card title="Create a roadmap">
        <form onSubmit={submit}>
          <ErrorBox error={create.error ? messageOf(create.error) : null} />
          <Field label="Your goal">
            <input className={inputCls} required minLength={3} maxLength={300} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="e.g. Learn Python, SQL and Docker for backend roles" />
            <span className="mt-1 block text-xs text-gray-500">Name the skills you want to learn; the plan is built around them.</span>
          </Field>
          <fieldset className="mb-3">
            <legend className="mb-1 text-sm font-medium">Duration</legend>
            {ROADMAP_DURATIONS.map((d) => (
              <label key={d} className="mr-4 text-sm">
                <input type="radio" name="duration" checked={days === d} onChange={() => setDays(d)} /> {d} days
              </label>
            ))}
          </fieldset>
          <Button type="submit" busy={create.isPending}>Create roadmap</Button>
        </form>
      </Card>
      <Card title="Your roadmaps">
        {list.isLoading && <Spinner />}
        {list.error && <ErrorBox error={messageOf(list.error)} />}
        {list.data?.length === 0 && <p className="text-sm text-gray-500">No roadmaps yet.</p>}
        <ul>
          {list.data?.map((r) => (
            <li key={r.id} className="border-t py-2 text-sm first:border-0">
              <Link className="font-medium text-blue-700 underline" to={`/learning/${r.id}`}>{r.title}</Link>
              {" · "}{r.duration_days} days · {r.status.replace("_", " ")} · {r.percent_required_complete}% of required work done
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

export function LearningDetail() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["roadmap", id], queryFn: () => request<Roadmap>(`/learning/roadmaps/${id}`) });
  const act = useMutation({
    mutationFn: (v: { path: string }) => request<Roadmap>(`/learning/roadmaps/${id}/${v.path}`, { method: "POST" }),
    onSuccess: (data) => { qc.setQueryData(["roadmap", id], data); void qc.invalidateQueries({ queryKey: ["roadmaps"] }); },
  });
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorBox error={messageOf(q.error)} />;
  const r = q.data;
  return (
    <>
      <h1 className="mb-1 text-2xl font-bold">{r.title}</h1>
      <p className="mb-3 text-sm text-gray-700">
        {r.duration_days} days · about {r.estimated_hours ?? 0} hours · status: {r.status.replace("_", " ")}
      </p>
      <ErrorBox error={act.error ? messageOf(act.error) : null} />
      {r.status === "not_started" && <Button onClick={() => act.mutate({ path: "start" })}>Start roadmap</Button>}
      <Card title={`Progress: ${r.progress.percent_required_complete}% of required work`}>
        <ul className="text-sm">
          {r.progress.requirements.map((x) => (
            <li key={x.name}>{x.met ? "✔" : "○"} {x.name}</li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-gray-600">
          Assessment activities complete only when you pass the assessment; they cannot be ticked manually.
        </p>
      </Card>
      {r.modules.map((m) => (
        <Card key={m.id} title={`Module ${m.position}: ${m.title} (${m.completed}/${m.total})`}>
          <ul>
            {m.activities.map((a) => (
              <li key={a.id} className="flex items-start gap-2 border-t py-1 text-sm first:border-0">
                <input
                  type="checkbox"
                  aria-label={`Complete: ${a.title}`}
                  checked={!!a.completed_at}
                  disabled={a.kind === "assessment" || act.isPending || r.status === "not_started"}
                  onChange={(e) => act.mutate({ path: `activities/${a.id}/${e.target.checked ? "complete" : "reopen"}` })}
                />
                <span>
                  Day {a.day_number} · {a.title} <i className="text-gray-500">({a.kind}{a.estimated_minutes ? `, ${a.estimated_minutes} min` : ""})</i>
                  {a.kind === "assessment" && <Link className="ml-2 text-blue-700 underline" to="/assessments">Take assessment</Link>}
                </span>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </>
  );
}
