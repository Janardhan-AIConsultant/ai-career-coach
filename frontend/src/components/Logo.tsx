/** Brand mark (same artwork as /logo.svg). Decorative by default; the wordmark beside it carries the name. */
export function LogoMark({ size = 32, title }: { size?: number; title?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" role={title ? "img" : undefined} aria-label={title}
      aria-hidden={title ? undefined : true} focusable="false">
      <defs>
        <linearGradient id="acc-logo-bg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4f46e5" />
          <stop offset="0.6" stopColor="#2563eb" />
          <stop offset="1" stopColor="#0ea5e9" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill="url(#acc-logo-bg)" />
      <path d="M44 44A17 17 0 1 1 44 20" fill="none" stroke="#fff" strokeWidth="6" strokeLinecap="round" />
      <path d="M23 40L30 33L35 37L46 25M40 24.5H46.5V31" fill="none" stroke="#fbbf24" strokeWidth="3.6"
        strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="50" cy="14" r="2.2" fill="#fff" opacity="0.9" />
    </svg>
  );
}

/** Lockup: mark + two-line wordmark (name over a small tagline). */
export function Logo({ size = 36, light = false, tagline = true }: { size?: number; light?: boolean; tagline?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} />
      <span className="flex flex-col leading-none">
        <span className={`text-[17px] font-bold tracking-tight ${light ? "text-white" : "text-slate-900"}`}>
          <span className={light ? "text-sky-200" : "text-indigo-600"}>AI</span> Career Coach
        </span>
        {tagline && (
          <span className={`mt-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${light ? "text-white/70" : "text-slate-500"}`}>
            Plan · Learn · Certify
          </span>
        )}
      </span>
    </span>
  );
}
