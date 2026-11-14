import type { ReactNode } from "react";

export const Card = ({ title, subtitle, icon, children, className = "" }: {
  title?: string; subtitle?: string; icon?: string; children: ReactNode; className?: string;
}) => (
  <section className={`mb-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm ${className}`}>
    {title && (
      <header className="mb-3 flex items-start gap-3">
        {icon && <span aria-hidden className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-indigo-50 text-lg">{icon}</span>}
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          {subtitle && <p className="text-sm text-slate-500">{subtitle}</p>}
        </div>
      </header>
    )}
    {children}
  </section>
);

export const PageHeader = ({ title, subtitle, children }: { title: string; subtitle?: string; children?: ReactNode }) => (
  <div className="mb-6 rounded-2xl bg-gradient-to-r from-indigo-600 via-indigo-500 to-sky-500 p-6 text-white shadow">
    <h1 className="text-2xl font-bold md:text-3xl">{title}</h1>
    {subtitle && <p className="mt-1 max-w-3xl text-indigo-50">{subtitle}</p>}
    {children}
  </div>
);

export const ErrorBox = ({ error }: { error: string | null }) =>
  error ? (
    <p role="alert" className="mb-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      <span aria-hidden>⚠️</span>
      <span>{error}</span>
    </p>
  ) : null;

export const Notice = ({ children, tone = "warn" }: { children: ReactNode; tone?: "warn" | "info" }) => (
  <p className={`mb-4 flex items-start gap-2 rounded-xl border p-3 text-sm ${
    tone === "info" ? "border-sky-200 bg-sky-50 text-sky-900" : "border-amber-200 bg-amber-50 text-amber-900"}`}>
    <span aria-hidden>{tone === "info" ? "ℹ️" : "🔔"}</span>
    <span>{children}</span>
  </p>
);

type Variant = "primary" | "secondary" | "danger";
const VARIANT: Record<Variant, string> = {
  primary: "bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm",
  secondary: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
  danger: "bg-red-600 text-white hover:bg-red-700",
};

export function Button({ busy, variant = "primary", className = "", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean; variant?: Variant }) {
  return (
    <button
      {...p}
      disabled={p.disabled || busy}
      className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-400 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT[variant]} ${className}`}
    >
      {busy ? (<><span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />Working…</>) : p.children}
    </button>
  );
}

export const Field = ({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) => (
  <label className="mb-4 block text-sm">
    <span className="mb-1 block font-medium text-slate-800">{label}</span>
    {children}
    {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
  </label>
);

export const inputCls =
  "w-full rounded-xl border border-slate-300 bg-white p-2.5 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200";

const TONES = {
  green: "bg-emerald-50 text-emerald-800 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-800 ring-red-200",
  blue: "bg-sky-50 text-sky-800 ring-sky-200",
  gray: "bg-slate-100 text-slate-700 ring-slate-200",
  indigo: "bg-indigo-50 text-indigo-800 ring-indigo-200",
};
export type Tone = keyof typeof TONES;

export const Chip = ({ children, tone = "gray" }: { children: ReactNode; tone?: Tone }) => (
  <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]}`}>{children}</span>
);

export const Chips = ({ items, tone, empty = "None" }: { items: string[]; tone?: Tone; empty?: string }) =>
  items.length ? (
    <div className="flex flex-wrap gap-1.5">{items.map((x) => <Chip key={x} tone={tone}>{x}</Chip>)}</div>
  ) : (
    <p className="text-sm text-slate-500">{empty}</p>
  );

export const List = ({ items, empty = "None" }: { items: string[]; empty?: string }) =>
  items.length ? (
    <ul className="list-disc space-y-0.5 pl-5 text-sm text-slate-700">
      {items.map((x, i) => (<li key={i}>{x}</li>))}
    </ul>
  ) : (
    <p className="text-sm text-slate-500">{empty}</p>
  );

export const Spinner = ({ what = "Loading" }: { what?: string }) => (
  <p role="status" className="flex items-center gap-2 text-sm text-slate-500">
    <span aria-hidden className="h-4 w-4 animate-spin rounded-full border-2 border-slate-400 border-t-transparent" />
    {what}…
  </p>
);

export const Empty = ({ children }: { children: ReactNode }) => (
  <p className="rounded-xl border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500">{children}</p>
);

export const Stat = ({ label, value, hint }: { label: string; value: string | number; hint?: string }) => (
  <div className="rounded-2xl border border-slate-200 bg-white p-4 text-center shadow-sm">
    <div className="text-2xl font-bold text-slate-900">{value}</div>
    <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
    {hint && <div className="mt-1 text-xs text-slate-400">{hint}</div>}
  </div>
);

const scoreTone = (n: number) => (n >= 75 ? "#059669" : n >= 50 ? "#d97706" : "#dc2626");

export function ScoreRing({ value, label }: { value: number; label: string }) {
  const r = 52;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div className="relative h-36 w-36 shrink-0" role="img" aria-label={`${label}: ${value} out of 100`}>
      <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
        <circle cx="60" cy="60" r={r} fill="none" stroke="#e2e8f0" strokeWidth="10" />
        <circle cx="60" cy="60" r={r} fill="none" stroke={scoreTone(pct)} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * c} ${c}`} />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span aria-label="Overall match score" className="text-3xl font-bold text-slate-900">{value}/100</span>
        <span className="text-xs text-slate-500">{label}</span>
      </div>
    </div>
  );
}

export const Bar = ({ value, label, detail }: { value: number | null; label: string; detail?: string }) => (
  <div className="mb-2">
    <div className="flex justify-between text-sm">
      <span className="font-medium capitalize text-slate-700">{label}</span>
      <span className="text-slate-500">{value === null ? "n/a" : `${value}%`}</span>
    </div>
    <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
      <div className="h-full rounded-full" style={{ width: `${value ?? 0}%`, background: scoreTone(value ?? 0) }} />
    </div>
    {detail && <p className="mt-0.5 text-xs text-slate-500">{detail}</p>}
  </div>
);
