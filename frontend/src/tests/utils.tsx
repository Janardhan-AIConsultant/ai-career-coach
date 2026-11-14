import { render } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactElement } from "react";
import { useSession } from "../store/session";

export interface Call { method: string; path: string; body: unknown; headers: Headers }
type Handler = (call: Call) => { status?: number; body?: unknown } | Promise<{ status?: number; body?: unknown }>;

/** Route table keyed by "METHOD /path" (path relative to /api/v1, query string ignored). */
export function mockApi(routes: Record<string, Handler | unknown>) {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const u = new URL(String(input));
    const method = (init?.method ?? "GET").toUpperCase();
    const path = u.pathname.replace("/api/v1", "");
    let body: unknown = init?.body;
    if (typeof body === "string") { try { body = JSON.parse(body); } catch { /* keep */ } }
    const call = { method, path, body, headers: new Headers(init?.headers) };
    calls.push(call);
    const h = routes[`${method} ${path}`];
    if (h === undefined) return new Response(JSON.stringify({ error: { code: "not_found", message: "Not Found" } }), { status: 404 });
    const r = typeof h === "function" ? await (h as Handler)(call) : { body: h };
    return new Response(r.status === 204 ? null : JSON.stringify(r.body ?? {}), { status: r.status ?? 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return { calls, fn };
}

export function renderApp(ui: ReactElement, route = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

export const signIn = (role = "user") =>
  useSession.setState({ accessToken: "tok", ready: true, user: { id: "u1", email: "a@example.com", display_name: "Ann", role } });

export const reset = () => {
  useSession.setState({ accessToken: null, user: null, guestToken: null, ready: true });
  sessionStorage.clear();
  vi.unstubAllGlobals();
};
