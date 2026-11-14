import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Analyze from "../pages/Analyze";
import { mockApi, renderApp, reset, type Call } from "./utils";

afterEach(reset);

const MATCH = {
  match: {
    overall_score: 72.5,
    disclaimer: "Estimate only.",
    category_scores: [{ category: "skills", score: 80, weight: 0.5, detail: "4 of 5" }],
    matching_skills: [{ skill: "Python" }],
    partial_skills: [],
    missing_skills: [{ skill: "Kafka", level: "mandatory" }],
    recommendations: ["Learn Kafka"],
  },
};
const RESUME_A = {
  analysis: {
    quality: { score: 61, note: "Heuristic." },
    experience_summary: "Backend developer",
    technical_skills: [{ skill: "python" }],
    strengths: ["Clear skills section"],
    weaknesses: ["No metrics"],
    ats_recommendations: ["Add dates"],
  },
};
const JD_A = {
  analysis: { title: "Backend Engineer", mandatory_skills: ["kafka"], preferred_skills: [], optional_skills: [], responsibilities: ["Build APIs"] },
};
const GAP = {
  analysis: {
    summary: "1 gap found",
    gaps: [
      {
        skill: "kafka",
        severity: "high",
        status: "missing",
        suggested_timeline_days: 15,
        current_evidence: "Not on resume",
        learning_recommendations: ["Learn topics and partitions"],
      },
    ],
  },
};

const guestRoutes = () => ({
  "POST /guest/sessions": (() => {
    let n = 0;
    return () => ({ status: 201, body: { token: n++ === 0 ? "GT" : "GT-second-session", session_id: "s1" } });
  })(),
  "POST /guest/documents": (c: Call) => ({
    status: 201,
    body: { document_id: (c.body as FormData).get("kind") === "resume" ? "d-r" : "d-j" },
  }),
  "POST /guest/resume/analyze": RESUME_A,
  "POST /guest/job-description/analyze": JD_A,
  "POST /guest/career/match": MATCH,
  "POST /guest/career/skill-gap": GAP,
});

const follows = (a: Node, b: Node) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

test("resume and job description sit side by side and the match button waits for both", async () => {
  mockApi(guestRoutes());
  renderApp(<Analyze />);
  const resume = screen.getByLabelText("Resume");
  const jd = screen.getByLabelText("Job description");
  const grid = (el: HTMLElement) => el.closest("div.grid");
  expect(grid(resume)).not.toBeNull();
  expect(grid(resume)).toBe(grid(jd)); // one shared two-column grid
  expect(grid(resume)?.className).toContain("md:grid-cols-2");
  const run = screen.getByRole("button", { name: /Analyse and match/ });
  expect(run).toBeDisabled();
  await userEvent.type(resume, "Python developer with SQL");
  expect(run).toBeDisabled();
  await userEvent.type(jd, "Need Python and Kafka");
  expect(run).toBeEnabled();
  expect(follows(resume, run) && follows(jd, run)).toBe(true); // the button is below both inputs
});

test("one click runs everything and shows match, skill gaps and analysis below the button", async () => {
  const { calls } = mockApi(guestRoutes());
  renderApp(<Analyze />);
  expect(screen.getByText(/temporary guest session/i)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Resume"), "Python developer with SQL");
  await userEvent.type(screen.getByLabelText("Job description"), "Need Python and Kafka");
  const run = screen.getByRole("button", { name: /Analyse and match/ });
  await userEvent.click(run);

  const score = await screen.findByLabelText("Overall match score");
  expect(score).toHaveTextContent("72.5/100");
  expect(screen.getByText("Estimate only.")).toBeInTheDocument();
  expect(screen.getByText("Kafka (mandatory)")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Skill gap analysis" })).toBeInTheDocument();
  expect(screen.getByText("Learn topics and partitions")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Resume analysis" })).toBeInTheDocument();
  expect(screen.getByText(/Job description: Backend Engineer/)).toBeInTheDocument();
  expect(follows(run, score)).toBe(true);
  expect(follows(score, screen.getByRole("heading", { name: "Skill gap analysis" }))).toBe(true); // gaps come after the match

  expect(calls.filter((c) => c.path === "/guest/sessions")).toHaveLength(1); // both uploads share one session
  const uploads = calls.filter((c) => c.path === "/guest/documents");
  expect(uploads).toHaveLength(2);
  expect(uploads[1].headers.get("X-Guest-Token")).toBe("GT");
  const order = calls.map((c) => c.path);
  const before = (a: string, b: string) => expect(order.indexOf(a)).toBeLessThan(order.indexOf(b));
  before("/guest/resume/analyze", "/guest/career/match");
  before("/guest/job-description/analyze", "/guest/career/match");
  before("/guest/career/match", "/guest/career/skill-gap");
  expect(calls.find((c) => c.path === "/guest/career/match")?.body).toMatchObject({
    resume_document_id: "d-r",
    job_description_document_id: "d-j",
  });
  expect(sessionStorage.getItem("acc.guest")).toBe("GT");
});

test("sample data fills both boxes and a chosen file replaces pasting", async () => {
  mockApi(guestRoutes());
  renderApp(<Analyze />);
  const samples = screen.getAllByRole("button", { name: /Use sample/ });
  await userEvent.click(samples[0]);
  await userEvent.click(samples[1]);
  expect((screen.getByLabelText("Resume") as HTMLTextAreaElement).value).toContain("Priya Sharma");
  expect((screen.getByLabelText("Job description") as HTMLTextAreaElement).value).toContain("Backend Engineer");
  await userEvent.upload(screen.getByLabelText("Resume file"), new File(["resume body"], "cv.txt", { type: "text/plain" }));
  expect(screen.getByLabelText("Resume")).toBeDisabled();
  expect(screen.getByText("cv.txt")).toBeInTheDocument();
});

test("an uploaded file is sent as a file, not as text", async () => {
  const { calls } = mockApi(guestRoutes());
  renderApp(<Analyze />);
  await userEvent.upload(screen.getByLabelText("Resume file"), new File(["resume body"], "cv.txt", { type: "text/plain" }));
  await userEvent.type(screen.getByLabelText("Job description"), "Need Python and Kafka");
  await userEvent.click(screen.getByRole("button", { name: /Analyse and match/ }));
  await screen.findByLabelText("Overall match score");
  const up = calls.find((c) => c.path === "/guest/documents" && (c.body as FormData).get("kind") === "resume");
  expect((up?.body as FormData).get("file")).toBeInstanceOf(File);
  expect((up?.body as FormData).get("text")).toBeNull();
});

test("the optimiser runs only when asked and needs approval for significant changes", async () => {
  const { calls } = mockApi({
    ...guestRoutes(),
    "POST /guest/resume/optimize": {
      result: {
        optimized_resume_text: "Text",
        pending_approval_ids: ["c1"],
        needs_confirmation: [],
        clarification_questions: ["Do you know Kafka?"],
        changes: [{ id: "c1", section: "skills", change_type: "significant", before: "", after: "Kafka", reason: "Job asks for it", applied: false }],
      },
    },
  });
  renderApp(<Analyze />);
  await userEvent.type(screen.getByLabelText("Resume"), "Python developer with SQL");
  await userEvent.type(screen.getByLabelText("Job description"), "Need Python and Kafka");
  await userEvent.click(screen.getByRole("button", { name: /Analyse and match/ }));
  await screen.findByLabelText("Overall match score");
  expect(calls.some((c) => c.path === "/guest/resume/optimize")).toBe(false); // nothing is rewritten until asked
  await userEvent.click(screen.getByRole("button", { name: "Optimise my resume" }));
  const box = await screen.findByRole("checkbox", { name: /Approve this change/ });
  expect(box).not.toBeChecked();
  expect(screen.getByText("needs your approval")).toBeInTheDocument();
  expect(calls.find((c) => c.path === "/guest/resume/optimize")?.body).toMatchObject({ approved_change_ids: [] });
  await userEvent.click(box);
  await userEvent.click(screen.getByRole("button", { name: "Run again with my approvals" }));
  await waitFor(() => expect(calls.filter((c) => c.path === "/guest/resume/optimize")).toHaveLength(2));
  expect(calls.filter((c) => c.path === "/guest/resume/optimize")[1].body).toMatchObject({ approved_change_ids: ["c1"] });
});
