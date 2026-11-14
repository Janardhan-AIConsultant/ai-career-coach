import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { request } from "../api/http";
import { useSession } from "../store/session";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-2 py-1 text-sm ${isActive ? "font-semibold text-blue-700" : "text-gray-700 hover:text-blue-700"}`;

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
    <div className="min-h-screen bg-gray-50 text-gray-900">
      <header className="border-b bg-white">
        <nav aria-label="Main" className="mx-auto flex max-w-5xl flex-wrap items-center gap-1 p-3">
          <Link to="/" className="mr-4 text-lg font-bold">
            AI Career Coach
          </Link>
          <NavLink to="/analyze" className={link}>Analyse</NavLink>
          <NavLink to="/testimonials" className={link}>Testimonials</NavLink>
          <NavLink to="/verify" className={link}>Verify certificate</NavLink>
          {user && (
            <>
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
                <span>{user.display_name}</span>
                <button onClick={signOut} className="text-blue-700 underline">Sign out</button>
              </>
            ) : (
              <>
                <NavLink to="/login" className={link}>Sign in</NavLink>
                <NavLink to="/register" className={link}>Register</NavLink>
              </>
            )}
          </span>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl p-4">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-5xl p-4 text-xs text-gray-500">
        Scores and reviews are automated estimates, not hiring decisions. Certificates are platform-issued,
        not externally accredited.
      </footer>
    </div>
  );
}
