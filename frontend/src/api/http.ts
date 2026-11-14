// Single place for backend access. Only VITE_API_BASE_URL is exposed to the browser.
import { useSession } from "../store/session";

// Set VITE_API_BASE_URL to "" in production to call same-origin /api/... (proxied by the host's rewrite).
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
/** Versioned API root. Trailing slashes are ignored, so VITE_API_BASE_URL="/" means same-origin /api/v1. */
export const API_ROOT = `${API_BASE_URL.replace(/\/+$/, "")}/api/v1`;
const API = API_ROOT;

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public fields: { field: string; message: string }[] = [],
  ) {
    super(message);
  }
}

type Auth = "user" | "guest" | "none";
export interface RequestOptions {
  method?: string;
  json?: unknown;
  form?: FormData;
  auth?: Auth;
  query?: Record<string, string | number | boolean | undefined | null>;
  signal?: AbortSignal;
}

let refreshing: Promise<boolean> | null = null;

/** Exchange the HttpOnly refresh cookie for a new access token. Concurrent callers share one request. */
export function refreshSession(): Promise<boolean> {
  if (refreshing) return refreshing;
  const attempt = (async () => {
    try {
      const res = await fetch(`${API}/auth/refresh`, { method: "POST", credentials: "include" });
      if (!res.ok) return false;
      const body = (await res.json()) as { access_token: string };
      useSession.getState().setAuth(body.access_token);
      return true;
    } catch {
      return false;
    }
  })();
  refreshing = attempt;
  // Forget the finished attempt immediately so a later 401 triggers a fresh refresh.
  void attempt.finally(() => {
    if (refreshing === attempt) refreshing = null;
  });
  return attempt;
}

function headersFor(auth: Auth, hasJson: boolean): Headers {
  const h = new Headers();
  if (hasJson) h.set("Content-Type", "application/json");
  const s = useSession.getState();
  if (auth === "user" && s.accessToken) h.set("Authorization", `Bearer ${s.accessToken}`);
  if (auth === "guest" && s.guestToken) h.set("X-Guest-Token", s.guestToken);
  return h;
}

async function toError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const e = body?.error;
    if (e) return new ApiError(res.status, e.code ?? "error", e.message ?? "Request failed", e.fields ?? []);
  } catch {
    /* not JSON */
  }
  return new ApiError(res.status, "error", `Request failed (${res.status})`);
}

function url(path: string, query?: RequestOptions["query"]): string {
  const u = new URL(`${API}${path}`, window.location.origin); // API may be a same-origin path (Vercel rewrite)
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined && v !== null && v !== "") u.searchParams.set(k, String(v));
  return u.toString();
}

async function send(path: string, o: RequestOptions, retried: boolean): Promise<Response> {
  const auth = o.auth ?? "user";
  const res = await fetch(url(path, o.query), {
    method: o.method ?? (o.json || o.form ? "POST" : "GET"),
    headers: headersFor(auth, o.json !== undefined),
    body: o.form ?? (o.json !== undefined ? JSON.stringify(o.json) : undefined),
    credentials: path.startsWith("/auth/") ? "include" : "same-origin",
    signal: o.signal,
  });
  if (res.status === 401 && auth === "user" && !retried && useSession.getState().accessToken) {
    if (await refreshSession()) return send(path, o, true);
    useSession.getState().clear();
  }
  return res;
}

export async function request<T>(path: string, o: RequestOptions = {}): Promise<T> {
  const res = await send(path, o, false);
  if (!res.ok) throw await toError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Fetch a protected file and hand it to the browser as a download (headers cannot be set on a plain link). */
export async function download(path: string, fallbackName: string, o: RequestOptions = {}): Promise<void> {
  const res = await send(path, o, false);
  if (!res.ok) throw await toError(res);
  const blob = await res.blob();
  const match = /filename="?([^";]+)"?/.exec(res.headers.get("Content-Disposition") ?? "");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = match?.[1] ?? fallbackName;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export const messageOf = (e: unknown): string =>
  e instanceof ApiError ? e.message : e instanceof Error ? e.message : "Something went wrong";
