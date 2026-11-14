import type { ReactNode } from "react";

export const Card = ({ title, children }: { title?: string; children: ReactNode }) => (
  <section className="mb-4 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
    {title && <h2 className="mb-2 text-lg font-semibold">{title}</h2>}
    {children}
  </section>
);

export const ErrorBox = ({ error }: { error: string | null }) =>
  error ? (
    <p role="alert" className="mb-3 rounded border border-red-300 bg-red-50 p-2 text-sm text-red-800">
      {error}
    </p>
  ) : null;

export const Notice = ({ children }: { children: ReactNode }) => (
  <p className="mb-3 rounded border border-amber-300 bg-amber-50 p-2 text-sm text-amber-900">{children}</p>
);

export function Button({ busy, className = "", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { busy?: boolean }) {
  return (
    <button
      {...p}
      disabled={p.disabled || busy}
      className={`rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50 ${className}`}
    >
      {busy ? "Working…" : p.children}
    </button>
  );
}

export const Field = ({ label, children }: { label: string; children: ReactNode }) => (
  <label className="mb-3 block text-sm">
    <span className="mb-1 block font-medium">{label}</span>
    {children}
  </label>
);

export const inputCls = "w-full rounded border border-gray-300 p-2 text-sm";

export const List = ({ items, empty = "None" }: { items: string[]; empty?: string }) =>
  items.length ? (
    <ul className="list-disc pl-5 text-sm">
      {items.map((x, i) => (
        <li key={i}>{x}</li>
      ))}
    </ul>
  ) : (
    <p className="text-sm text-gray-500">{empty}</p>
  );

export const Spinner = ({ what = "Loading" }: { what?: string }) => (
  <p role="status" className="text-sm text-gray-500">
    {what}…
  </p>
);
