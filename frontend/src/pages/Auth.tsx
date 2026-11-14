import { FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { request, messageOf } from "../api/http";
import { AuthShell } from "../components/AuthShell";
import { Button, Card, ErrorBox, Field, inputCls } from "../components/ui";
import { useSession, type User } from "../store/session";

async function finish(token: string): Promise<User> {
  useSession.getState().setAuth(token);
  const user = await request<User>("/users/me");
  useSession.getState().setAuth(token, user);
  return user;
}

export function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from ?? "/learning";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const t = await request<{ access_token: string }>("/auth/login", { json: { email, password }, auth: "none" });
      await finish(t.access_token);
      nav(from, { replace: true });
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell headline="Pick up where your career growth left off" points={["Your roadmaps and progress, saved","Certificates you can share and verify","A coach that knows your skill gaps"]}><Card title="Welcome back" subtitle="Sign in to continue your learning" icon="🔐">
      <form onSubmit={submit}>
        <ErrorBox error={error} />
        <Field label="Email">
          <input className={inputCls} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password">
          <input className={inputCls} type="password" required autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button type="submit" busy={busy}>Sign in</Button>
        <p className="mt-3 text-sm">
          No account? <Link className="text-blue-700 underline" to="/register">Register</Link>
        </p>
      </form>
    </Card></AuthShell>
  );
}

export function Register() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nav = useNavigate();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const t = await request<{ access_token: string }>("/auth/register", {
        json: { email, password, display_name: name },
        auth: "none",
      });
      await finish(t.access_token);
      nav("/learning", { replace: true });
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthShell headline="Turn your next job into a plan" points={["Match score and skill gaps in minutes","7, 15 or 60 day learning roadmaps","Assessments and platform-issued certificates"]}><Card title="Create your account" subtitle="Free. Keep your history, roadmaps and certificates." icon="🚀">
      <form onSubmit={submit}>
        <ErrorBox error={error} />
        <Field label="Display name">
          <input className={inputCls} required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Email">
          <input className={inputCls} type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </Field>
        <Field label="Password (at least 10 characters, mixed)">
          <input className={inputCls} type="password" required minLength={10} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </Field>
        <Button type="submit" busy={busy}>Create account</Button>
        <p className="mt-3 text-sm">
          Already registered? <Link className="text-blue-700 underline" to="/login">Sign in</Link>
        </p>
      </form>
    </Card></AuthShell>
  );
}
