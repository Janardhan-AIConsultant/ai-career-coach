import { useEffect } from "react";
import { Route, Routes } from "react-router-dom";
import { refreshSession, request } from "./api/http";
import Layout from "./components/Layout";
import { RequireAdmin, RequireUser } from "./components/Guards";
import { useSession, type User } from "./store/session";
import { AdminHome } from "./pages/Admin";
import Analyze from "./pages/Analyze";
import Assessments from "./pages/Assessments";
import { Login, Register } from "./pages/Auth";
import { Certificates, Verify } from "./pages/Certificates";
import Coach from "./pages/Coach";
import Home from "./pages/Home";
import { LearningDetail, LearningList } from "./pages/Learning";
import { PortfolioPage, PublicPortfolio } from "./pages/Portfolio";
import { Feedback, PublicTestimonialPage, PublicTestimonials } from "./pages/Testimonials";

/** Restore a session from the HttpOnly refresh cookie once on load. */
function useBootstrap() {
  const setReady = useSession((s) => s.setReady);
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (await refreshSession()) {
          const user = await request<User>("/users/me");
          if (alive) useSession.getState().setUser(user);
        }
      } catch {
        /* not signed in */
      } finally {
        if (alive) setReady();
      }
    })();
    return () => {
      alive = false;
    };
  }, [setReady]);
}

export default function App() {
  useBootstrap();
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="analyze" element={<Analyze />} />
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        <Route path="testimonials" element={<PublicTestimonials />} />
        <Route path="testimonials/:id" element={<PublicTestimonialPage />} />
        <Route path="verify" element={<Verify />} />
        <Route path="verify/:id" element={<Verify />} />
        <Route path="portfolio/:slug" element={<PublicPortfolio />} />
        <Route element={<RequireUser />}>
          <Route path="learning" element={<LearningList />} />
          <Route path="learning/:id" element={<LearningDetail />} />
          <Route path="assessments" element={<Assessments />} />
          <Route path="coach" element={<Coach />} />
          <Route path="certificates" element={<Certificates />} />
          <Route path="portfolio" element={<PortfolioPage />} />
          <Route path="feedback" element={<Feedback />} />
        </Route>
        <Route element={<RequireAdmin />}>
          <Route path="admin" element={<AdminHome />} />
        </Route>
        <Route path="*" element={<p role="alert">Page not found.</p>} />
      </Route>
    </Routes>
  );
}
