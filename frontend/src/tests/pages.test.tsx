import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { RequireAdmin, RequireUser } from "../components/Guards";
import { Login } from "../pages/Auth";
import { LearningList } from "../pages/Learning";
import { PortfolioPage } from "../pages/Portfolio";
import { Feedback, ShareButtons } from "../pages/Testimonials";
import { useSession } from "../store/session";
import { mockApi, renderApp, reset, signIn } from "./utils";

afterEach(reset);

test("sign in stores the token in memory and loads the user", async () => {
  const { calls } = mockApi({
    "POST /auth/login": { access_token: "T1", token_type: "bearer", expires_in: 1800 },
    "GET /users/me": { id: "u", email: "a@example.com", display_name: "Ann", role: "user" },
  });
  renderApp(
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/learning" element={<p>Learning page</p>} />
    </Routes>,
    "/login",
  );
  await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "Str0ng-passw0rd");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByText("Learning page")).toBeInTheDocument();
  expect(useSession.getState().accessToken).toBe("T1");
  expect(calls.find((c) => c.path === "/users/me")?.headers.get("Authorization")).toBe("Bearer T1");
});

test("sign in shows the server message on failure and keeps the user signed out", async () => {
  mockApi({
    "POST /auth/login": () => ({ status: 401, body: { error: { code: "authentication_error", message: "Invalid email or password" } } }),
  });
  renderApp(<Login />);
  await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "wrong");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
  expect(useSession.getState().accessToken).toBeNull();
});

test("protected routes send visitors to sign in; admin routes refuse ordinary users", () => {
  const tree = (
    <Routes>
      <Route path="/login" element={<p>Login screen</p>} />
      <Route element={<RequireUser />}>
        <Route path="/secret" element={<p>Secret</p>} />
      </Route>
      <Route element={<RequireAdmin />}>
        <Route path="/admin" element={<p>Admin screen</p>} />
      </Route>
    </Routes>
  );
  const first = renderApp(tree, "/secret");
  expect(screen.getByText("Login screen")).toBeInTheDocument();
  first.unmount();
  signIn("user");
  const second = renderApp(tree, "/admin");
  expect(screen.getByRole("alert")).toHaveTextContent("Administrator access is required");
  second.unmount();
  signIn("admin");
  renderApp(tree, "/admin");
  expect(screen.getByText("Admin screen")).toBeInTheDocument();
});

test("roadmap creation offers exactly 7, 15 and 60 days and posts the choice", async () => {
  signIn();
  const { calls } = mockApi({ "GET /learning/roadmaps": [], "POST /learning/roadmaps": { id: "r1" } });
  renderApp(<LearningList />);
  const radios = screen.getAllByRole("radio");
  expect(radios.map((r) => r.parentElement?.textContent?.trim())).toEqual(["7 days", "15 days", "60 days"]);
  await userEvent.type(screen.getByLabelText(/Your goal/), "Backend engineer");
  await userEvent.click(radios[1]);
  await userEvent.click(screen.getByRole("button", { name: "Create roadmap" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/learning/roadmaps")).toBe(true));
  expect(calls.find((c) => c.method === "POST")?.body).toEqual({ duration_days: 15, goal: "Backend engineer" });
});

test("testimonial consent is not pre-ticked and is sent as false unless the user agrees", async () => {
  signIn();
  const { calls } = mockApi({ "GET /testimonials": [], "POST /testimonials": { id: "t1" } });
  renderApp(<Feedback />);
  expect(screen.getByRole("checkbox", { name: /may be shown publicly/i })).not.toBeChecked();
  await userEvent.type(screen.getByLabelText(/Your testimonial/), "This platform gave me a clear plan and confidence.");
  await userEvent.click(screen.getByRole("button", { name: "Submit testimonial" }));
  await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === "/testimonials")).toBe(true));
  const body = calls.find((c) => c.method === "POST" && c.path === "/testimonials")?.body as { public_consent: boolean };
  expect(body.public_consent).toBe(false);
});

test("share buttons are limited to LinkedIn, WhatsApp and Facebook and never post anything", async () => {
  signIn();
  const links = {
    linkedin: "https://www.linkedin.com/sharing/share-offsite/?url=u",
    whatsapp: "https://wa.me/?text=t",
    facebook: "https://www.facebook.com/sharer/sharer.php?u=u",
  };
  const { calls } = mockApi({
    "GET /testimonials/t1/share": { public_url: "http://x/testimonials/t1", share_text: "Great - Ann", links, note: "This platform never posts for you." },
    "POST /testimonials/public/t1/events": () => ({ status: 204 }),
  });
  renderApp(<ShareButtons id="t1" />);
  const anchors = await screen.findAllByRole("link");
  expect(anchors.map((a) => a.textContent)).toEqual(["Share on LinkedIn", "Share on WhatsApp", "Share on Facebook", "Download card (PNG)"]);
  expect(document.body.textContent?.toLowerCase()).not.toMatch(/twitter|telegram|x\.com/);
  anchors.slice(0, 3).forEach((a) => expect(a).toHaveAttribute("rel", "noopener noreferrer"));
  anchors[0].addEventListener("click", (e) => e.preventDefault()); // jsdom cannot navigate
  await userEvent.click(anchors[0]);
  await waitFor(() => expect(calls.some((c) => c.path.endsWith("/events"))).toBe(true));
  expect(calls.find((c) => c.path.endsWith("/events"))?.body).toEqual({ event_type: "share_click", platform: "linkedin" });
});

test("publishing a portfolio needs both consent and a display name", async () => {
  signIn();
  const portfolio = {
    settings: { visibility: "private", public_slug: null, public_url: null, display_name: null, headline: null, summary: null, resume_integration_approved: false },
    timeline: [],
    skills: [],
    stats: { learning_paths_completed: 0, assessments_passed: 0, certificates: 0, projects_passed: 0 },
    disclaimer: "Not professional employment experience.",
  };
  const { calls } = mockApi({ "GET /portfolio": portfolio, "PUT /portfolio/settings": portfolio });
  renderApp(<PortfolioPage />);
  const publish = await screen.findByRole("button", { name: "Make public" });
  expect(publish).toBeDisabled();
  await userEvent.type(screen.getByLabelText(/display name/i), "Ann L.");
  expect(publish).toBeDisabled();
  await userEvent.click(screen.getByRole("checkbox", { name: /I consent/i }));
  expect(publish).toBeEnabled();
  await userEvent.click(publish);
  await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
  expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ visibility: "public", consent_public: true, display_name: "Ann L." });
});
