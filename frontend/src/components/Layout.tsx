import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { request } from "../api/http";
import { Logo, LogoMark } from "./Logo";
import { useSession } from "../store/session";

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-lg px-3 py-1.5 text-sm font-medium transition ${
    isActive ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`;

export default function Layout() {
  const { user, clear } = useSession();
  const nav = useNavigate();
  const signOut = async () => {
    try {
      await request("/auth/logout", { method: "POST", auth: "none" });
    } finally {
      clear();
      nav("/");
    }
  };
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/90 backdrop-blur">
        <nav aria-label="Main" className="mx-auto flex max-w-6xl flex-wrap items-center gap-1 px-4 py-2.5">
          <Link to="/" className="flex items-center" aria-label="AI Career Coach home">
            <Logo />
          </Link>
          <span aria-hidden className="mx-4 hidden h-8 w-px bg-slate-200 lg:block" />
          <NavLink to="/analyze" className={link}>Analyse</NavLink>
          <NavLink to="/testimonials" className={link}>Testimonials</NavLink>
          <NavLink to="/verify" className={link}>Verify certificate</NavLink>
          {user && (
            <>
              <span aria-hidden className="mx-1 hidden h-5 w-px bg-slate-200 md:block" />
              <NavLink to="/learning" className={link}>Learning</NavLink>
              <NavLink to="/assessments" className={link}>Assessments</NavLink>
              <NavLink to="/coach" className={link}>Coach</NavLink>
              <NavLink to="/certificates" className={link}>Certificates</NavLink>
              <NavLink to="/portfolio" className={link}>Portfolio</NavLink>
              <NavLink to="/feedback" className={link}>Feedback</NavLink>
              {user.role === "admin" && <NavLink to="/admin" className={link}>Admin</NavLink>}
            </>
          )}
          <span className="ml-auto flex items-center gap-2 text-sm">
            {user ? (
              <>
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-100 font-semibold text-indigo-700" aria-hidden>
                  {user.display_name.slice(0, 1).toUpperCase()}
                </span>
                <span className="hidden text-slate-700 sm:inline">{user.display_name}</span>
                <button onClick={signOut} className="rounded-lg border border-slate-300 px-3 py-1.5 font-medium text-slate-700 hover:bg-slate-50">Sign out</button>
              </>
            ) : (
              <>
                <NavLink to="/login" className={link}>Sign in</NavLink>
                <Link to="/register" className="rounded-lg bg-indigo-600 px-3 py-1.5 font-semibold text-white hover:bg-indigo-700">Register</Link>
              </>
            )}
          </span>
        </nav>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">
        <Outlet />
      </main>
      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-start gap-3 px-4 py-4">
          <LogoMark size={24} />
          <p className="text-xs text-slate-500">
          Scores and reviews are automated estimates, not hiring decisions. Certificates are platform-issued, not
          externally accredited. This platform never posts to social networks on your behalf.
          </p>
        </div>
      </footer>
    </div>
  );
}
