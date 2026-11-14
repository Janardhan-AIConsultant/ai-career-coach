import type { ReactNode } from "react";
import { Logo } from "./Logo";

/** Illustration: a climbing path of milestones (resume -> match -> roadmap -> certificate). Decorative only. */
function CareerPath() {
  return (
    <svg viewBox="0 0 420 260" className="mx-auto w-full max-w-md" aria-hidden focusable="false">
      <defs>
        <linearGradient id="auth-trail" x1="0" y1="1" x2="1" y2="0">
          <stop offset="0" stopColor="#a5b4fc" stopOpacity="0.2" />
          <stop offset="1" stopColor="#fde68a" />
        </linearGradient>
      </defs>
      <path d="M20 230 C110 230 120 170 190 160 S300 120 330 60" fill="none" stroke="url(#auth-trail)" strokeWidth="6"
        strokeLinecap="round" strokeDasharray="2 12" />
      {/* milestone 1: resume */}
      <g transform="translate(30 168)">
        <rect width="64" height="76" rx="10" fill="#fff" opacity="0.95" />
        <rect x="12" y="14" width="26" height="6" rx="3" fill="#6366f1" />
        <rect x="12" y="28" width="40" height="4" rx="2" fill="#cbd5e1" />
        <rect x="12" y="38" width="36" height="4" rx="2" fill="#cbd5e1" />
        <rect x="12" y="48" width="40" height="4" rx="2" fill="#cbd5e1" />
        <rect x="12" y="58" width="24" height="4" rx="2" fill="#cbd5e1" />
      </g>
      {/* milestone 2: match score */}
      <g transform="translate(150 98)">
        <circle cx="38" cy="38" r="38" fill="#fff" opacity="0.95" />
        <circle cx="38" cy="38" r="28" fill="none" stroke="#e2e8f0" strokeWidth="8" />
        <circle cx="38" cy="38" r="28" fill="none" stroke="#10b981" strokeWidth="8" strokeLinecap="round"
          strokeDasharray="151 176" transform="rotate(-90 38 38)" />
        <text x="38" y="44" textAnchor="middle" fontSize="18" fontWeight="700" fill="#0f172a">86%</text>
      </g>
      {/* milestone 3: roadmap check */}
      <g transform="translate(262 120)">
        <rect width="86" height="34" rx="17" fill="#fff" opacity="0.95" />
        <circle cx="19" cy="17" r="10" fill="#10b981" />
        <path d="M14 17l4 4 7-8" fill="none" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <text x="36" y="22" fontSize="13" fontWeight="600" fill="#0f172a">Day 7</text>
      </g>
      {/* goal: certificate star */}
      <g transform="translate(300 14)">
        <rect width="92" height="64" rx="10" fill="#fff" opacity="0.97" />
        <rect x="8" y="8" width="76" height="48" rx="6" fill="none" stroke="#d4a017" strokeWidth="1.5" />
        <rect x="22" y="18" width="48" height="5" rx="2.5" fill="#1e3a8a" />
        <rect x="30" y="29" width="32" height="4" rx="2" fill="#cbd5e1" />
        <circle cx="46" cy="46" r="6" fill="#fbbf24" />
      </g>
      <circle cx="70" cy="40" r="3" fill="#fff" opacity="0.7" />
      <circle cx="230" cy="40" r="2" fill="#fff" opacity="0.6" />
      <circle cx="390" cy="150" r="3" fill="#fff" opacity="0.6" />
    </svg>
  );
}

export function AuthShell({ headline, points, children }: { headline: string; points: string[]; children: ReactNode }) {
  return (
    <div className="mx-auto mt-2 grid max-w-5xl overflow-hidden rounded-3xl bg-white shadow-xl ring-1 ring-slate-200 md:grid-cols-2">
      <aside className="relative overflow-hidden bg-gradient-to-br from-indigo-700 via-blue-600 to-sky-500 p-8 text-white">
        <div aria-hidden className="absolute -right-16 -top-16 h-56 w-56 rounded-full bg-white/10" />
        <div aria-hidden className="absolute -bottom-20 -left-10 h-64 w-64 rounded-full bg-white/10" />
        <div className="relative flex h-full flex-col">
          <Logo light size={40} />
          <h2 className="mt-6 text-2xl font-extrabold leading-snug md:text-3xl">{headline}</h2>
          <ul className="mt-4 space-y-2 text-sm text-white/90">
            {points.map((p) => (
              <li key={p} className="flex gap-2"><span aria-hidden className="text-amber-300">✓</span>{p}</li>
            ))}
          </ul>
          <div className="mt-6 hidden flex-1 items-end md:flex"><CareerPath /></div>
        </div>
      </aside>
      <div className="flex items-center bg-slate-50/60 p-6 md:p-10"><div className="w-full">{children}</div></div>
    </div>
  );
}
