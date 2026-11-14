import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useSession } from "../store/session";
import { Spinner } from "./ui";

/** Registered-user pages. Visitors are sent to sign in and returned afterwards. */
export function RequireUser() {
  const { user, ready } = useSession();
  const loc = useLocation();
  if (!ready) return <Spinner what="Checking your session" />;
  if (!user) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return <Outlet />;
}

/** Admin pages. The server enforces the role on every call; this only hides screens that would 403. */
export function RequireAdmin() {
  const { user, ready } = useSession();
  if (!ready) return <Spinner what="Checking your session" />;
  if (!user) return <Navigate to="/login" replace />;
  if (user.role !== "admin") return <p role="alert">Administrator access is required.</p>;
  return <Outlet />;
}
