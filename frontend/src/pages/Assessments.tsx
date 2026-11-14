import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { messageOf, request } from "../api/http";
import { Button, Card, ErrorBox, Spinner, inputCls } from "../components/ui";

interface Summary { slug: string; title: string; topic: string; difficulty: string; pass_score: number; question_count: number; attempts: number; best_score: number | null }
interface Question { id: string; type: string; prompt: string; options: string[] | null; points: number }
interface Detail extends Summary { questions: Question[] }
interface Feedback { question_id: string; status: string; feedback: string; explanation: string | null; points_earned: number; points_possible: number }
interface Result { score: number; passed: boolean; pass_score: number; results: Feedback[]; roadmap_activities_completed: number }

type Answer = string | string[];

export default function Assessments() {
  const [slug, setSlug] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["assessments"], queryFn: () => request<Summary[]>("/assessments") });
  if (slug) return <Take slug={slug} onDone={() => setSlug(null)} />;
  return (
    <>
      <h1 className="mb-3 text-2xl font-bold">Assessments</h1>
      {list.isLoading && <Spinner />}
      <ErrorBox error={list.error ? messageOf(list.error) : null} />
      <div className="grid gap-3 md:grid-cols-2">
        {list.data?.map((a) => (
          <Card key={a.slug} title={a.title}>
            <p className="text-sm text-gray-700">
              {a.topic} · {a.difficulty} · {a.question_count} questions · pass mark {a.pass_score}%
            </p>
            <p className="mb-2 text-sm">Attempts: {a.attempts}{a.best_score !== null ? ` · best ${a.best_score}%` : ""}</p>
            <Button onClick={() => setSlug(a.slug)}>Start</Button>
          </Card>
        ))}
      </div>
    </>
  );
}

function Take({ slug, onDone }: { slug: string; onDone: () => void }) {
  const qc = useQueryClient();
  const [answers, setAnswers] = useState<Record<string, Answer>>({});
  const q = useQuery({ queryKey: ["assessment", slug], queryFn: () => request<Detail>(`/assessments/${slug}`) });
  const submit = useMutation({
    mutationFn: () => request<Result>(`/assessments/${slug}/attempts`, { json: { answers } }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["assessments"] }); void qc.invalidateQueries({ queryKey: ["roadmaps"] }); },
  });
  if (q.isLoading) return <Spinner />;
  if (q.error || !q.data) return <ErrorBox error={messageOf(q.error)} />;
  const set = (id: string, v: Answer) => setAnswers((a) => ({ ...a, [id]: v }));
  const res = submit.data;
  const fb = (id: string) => res?.results.find((r) => r.question_id === id);

  return (
    <>
      <button className="mb-2 text-sm text-blue-700 underline" onClick={onDone}>← All assessments</button>
      <h1 className="mb-1 text-2xl font-bold">{q.data.title}</h1>
      <p className="mb-3 text-sm text-gray-700">Pass mark {q.data.pass_score}%. Scoring happens on the server; answers are revealed after you submit.</p>
      <ErrorBox error={submit.error ? messageOf(submit.error) : null} />
      {res && (
        <Card title={res.passed ? "Passed" : "Not passed yet"}>
          <p role="status" className="text-lg font-semibold">{res.score}% (pass mark {res.pass_score}%)</p>
          {res.roadmap_activities_completed > 0 && <p className="text-sm">{res.roadmap_activities_completed} roadmap activity(ies) completed.</p>}
        </Card>
      )}
      {q.data.questions.map((qu, i) => {
        const f = fb(qu.id);
        return (
          <Card key={qu.id} title={`${i + 1}. ${qu.prompt}`}>
            {(qu.type === "mcq" || qu.type === "multi_select") && qu.options ? (
              qu.options.map((o) => {
                const multi = qu.type === "multi_select";
                const cur = answers[qu.id];
                const checked = multi ? Array.isArray(cur) && cur.includes(o) : cur === o;
                return (
                  <label key={o} className="mb-1 block text-sm">
                    <input
                      type={multi ? "checkbox" : "radio"}
                      name={qu.id}
                      checked={checked}
                      disabled={!!res}
                      onChange={(e) =>
                        multi
                          ? set(qu.id, e.target.checked ? [...(Array.isArray(cur) ? cur : []), o] : (Array.isArray(cur) ? cur : []).filter((x) => x !== o))
                          : set(qu.id, o)
                      }
                    />{" "}
                    {o}
                  </label>
                );
              })
            ) : (
              <textarea className={inputCls} rows={4} maxLength={5000} disabled={!!res} aria-label={`Answer ${i + 1}`}
                value={typeof answers[qu.id] === "string" ? (answers[qu.id] as string) : ""} onChange={(e) => set(qu.id, e.target.value)} />
            )}
            {f && (
              <p className="mt-2 text-sm">
                <b>{f.status.replace("_", " ")}</b> ({f.points_earned}/{f.points_possible}). {f.feedback} {f.explanation}
              </p>
            )}
          </Card>
        );
      })}
      {!res && <Button busy={submit.isPending} onClick={() => submit.mutate()}>Submit answers</Button>}
    </>
  );
}
