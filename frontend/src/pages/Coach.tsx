import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { messageOf, request } from "../api/http";
import { Button, Card, ErrorBox, Spinner, inputCls } from "../components/ui";

interface Conversation { id: string; title: string; updated_at: string }
interface Message { id: string; role: "user" | "assistant"; content: string; sources?: { label?: string; filename?: string }[] | null }

export default function Coach() {
  const qc = useQueryClient();
  const [active, setActive] = useState<string | null>(null);
  const [text, setText] = useState("");
  const convs = useQuery({ queryKey: ["convs"], queryFn: () => request<Conversation[]>("/coach/conversations") });
  const msgs = useQuery({
    queryKey: ["msgs", active],
    enabled: !!active,
    queryFn: () => request<Message[]>(`/coach/conversations/${active}/messages`),
  });
  const create = useMutation({
    mutationFn: () => request<Conversation>("/coach/conversations", { json: {} }),
    onSuccess: (c) => { setActive(c.id); void qc.invalidateQueries({ queryKey: ["convs"] }); },
  });
  const send = useMutation({
    mutationFn: (content: string) => request(`/coach/conversations/${active}/messages`, { json: { content } }),
    onSuccess: () => { setText(""); void qc.invalidateQueries({ queryKey: ["msgs", active] }); },
  });
  const remove = useMutation({
    mutationFn: (id: string) => request(`/coach/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => { setActive(null); void qc.invalidateQueries({ queryKey: ["convs"] }); },
  });
  const submit = (e: FormEvent) => { e.preventDefault(); if (text.trim()) send.mutate(text.trim()); };

  return (
    <>
      <h1 className="mb-1 text-2xl font-bold">AI Career Coach</h1>
      <p className="mb-3 text-sm text-gray-700">
        Answers are grounded in your own documents. The coach cannot take actions for you (it cannot publish, apply or
        send anything).
      </p>
      <div className="grid gap-4 md:grid-cols-[14rem_1fr]">
        <div>
          <Button onClick={() => create.mutate()} busy={create.isPending}>New conversation</Button>
          {convs.isLoading && <Spinner />}
          <ul className="mt-2 text-sm">
            {convs.data?.map((c) => (
              <li key={c.id} className="flex justify-between gap-1 border-t py-1">
                <button className={`text-left ${active === c.id ? "font-semibold" : ""}`} onClick={() => setActive(c.id)}>{c.title}</button>
                <button aria-label={`Delete ${c.title}`} className="text-red-700" onClick={() => remove.mutate(c.id)}>×</button>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <ErrorBox error={[create, send, remove].map((m) => m.error).find(Boolean) ? messageOf([create, send, remove].map((m) => m.error).find(Boolean)) : null} />
          {!active ? (
            <p className="text-sm text-gray-500">Select or start a conversation.</p>
          ) : (
            <>
              <div className="mb-3" aria-live="polite">
                {msgs.data?.map((m) => (
                  <Card key={m.id}>
                    <p className="mb-1 text-xs font-semibold uppercase text-gray-500">{m.role === "user" ? "You" : "Coach"}</p>
                    <p className="whitespace-pre-wrap text-sm">{m.content}</p>
                    {m.sources && m.sources.length > 0 && (
                      <p className="mt-1 text-xs text-gray-500">Sources: {m.sources.map((s) => s.label ?? s.filename).join(", ")}</p>
                    )}
                  </Card>
                ))}
              </div>
              <form onSubmit={submit}>
                <textarea className={inputCls} rows={3} maxLength={4000} aria-label="Your message" value={text} onChange={(e) => setText(e.target.value)} />
                <Button type="submit" busy={send.isPending} className="mt-2">Send</Button>
              </form>
            </>
          )}
        </div>
      </div>
    </>
  );
}
