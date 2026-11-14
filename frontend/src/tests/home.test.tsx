import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Home from "../pages/Home";
import { mockApi, renderApp, reset } from "./utils";

afterEach(reset);

const T = (id: string, name: string, text: string, rating: number | null = 5) => ({
  id, display_name: name, text, rating, success_story: null, feature: "platform",
});

test("the landing page shows approved testimonials with names, ratings and the average", async () => {
  mockApi({
    "GET /testimonials/public": [T("1", "Omar L.", "The roadmap gave me a clear plan.", 5), T("2", "Anonymous learner", "Mock interviews built my confidence.", 4)],
    "GET /feedback/stats": { ratings_count: 12, average_rating: 4.6, testimonials_count: 2 },
  });
  renderApp(<Home />);
  expect(await screen.findByText(/The roadmap gave me a clear plan/)).toBeInTheDocument();
  expect(screen.queryByText(/Mock interviews built my confidence/)).toBeNull(); // one at a time
  expect(screen.getByText(/Omar L\./)).toBeInTheDocument();
  expect(screen.getByLabelText("5 out of 5")).toBeInTheDocument();
  expect(await screen.findByLabelText("Average rating 4.6 out of 5")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Read more stories" })).toHaveAttribute("href", "/testimonials");
  expect(screen.getByRole("link", { name: "Start your own journey" })).toHaveAttribute("href", "/analyze");
});

test("with no published testimonials nothing is invented; an invitation is shown instead", async () => {
  mockApi({
    "GET /testimonials/public": [],
    "GET /feedback/stats": { ratings_count: 0, average_rating: null, testimonials_count: 0 },
  });
  renderApp(<Home />);
  expect(await screen.findByText(/No testimonials have been published yet/)).toBeInTheDocument();
  expect(screen.queryByRole("blockquote")).toBeNull();
  expect(screen.queryByText(/average from/)).toBeNull();
  expect(screen.queryByRole("link", { name: "Read more stories" })).toBeNull();
});

test("if the testimonials request fails the rest of the landing page still renders", async () => {
  mockApi({
    "GET /testimonials/public": () => ({ status: 500, body: { error: { code: "internal_error", message: "x" } } }),
    "GET /feedback/stats": () => ({ status: 500, body: { error: { code: "internal_error", message: "x" } } }),
  });
  renderApp(<Home />);
  expect(await screen.findByRole("heading", { name: /Know exactly how you match a job/ })).toBeInTheDocument();
  await screen.findByText("Try it right now, no account");
  expect(screen.queryByText(/Learners like you/)).toBeNull();
});

const five = () => ({
  "GET /testimonials/public": [1, 2, 3, 4, 5].map((n) => T(String(n), `Person ${n}`, `Story number ${n} about progress.`)),
  "GET /feedback/stats": { ratings_count: 0, average_rating: null, testimonials_count: 5 },
});

test("testimonials rotate automatically, one at a time, and wrap around", async () => {
  mockApi(five());
  vi.useFakeTimers({ shouldAdvanceTime: true }); // installed before render so the rotation interval is faked
  try {
    renderApp(<Home />);
    await screen.findByText(/Story number 1 about progress/);
    expect(screen.getAllByText(/Person \d/)).toHaveLength(1);
    act(() => { vi.advanceTimersByTime(5000); });
    expect(screen.getByText(/Story number 2 about progress/)).toBeInTheDocument();
    expect(screen.queryByText(/Story number 1 about progress/)).toBeNull();
    act(() => { vi.advanceTimersByTime(5000 * 4); });
    expect(screen.getByText(/Story number 1 about progress/)).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

test("visitors can jump to a testimonial with the dots and pause the rotation", async () => {
  mockApi(five());
  renderApp(<Home />);
  await screen.findByText(/Story number 1 about progress/);
  expect(screen.getAllByRole("button", { name: /Show testimonial \d of 5/ })).toHaveLength(5);
  await userEvent.click(screen.getByRole("button", { name: "Show testimonial 4 of 5" }));
  expect(screen.getByText(/Story number 4 about progress/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Pause rotation" }));
  vi.useFakeTimers();
  try {
    act(() => { vi.advanceTimersByTime(20000); });
    expect(screen.getByText(/Story number 4 about progress/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume rotation" })).toBeInTheDocument();
  } finally {
    vi.useRealTimers();
  }
});

test("the testimonials sit on the left and the video on the right of the same row", async () => {
  mockApi(five());
  const { container } = renderApp(<Home />);
  await screen.findByText(/Story number 1 about progress/);
  const row = container.querySelector("section[aria-labelledby='stories']")!.parentElement!;
  expect(row.children[0].getAttribute("aria-labelledby")).toBe("stories");
  expect(row.children[1].getAttribute("aria-labelledby")).toBe("intro-video");
});

test("sample testimonials are labelled as samples, never presented as real words", async () => {
  mockApi({
    "GET /testimonials/public": [T("1", "Sample learner (demo)", "A sample story about a plan.")],
    "GET /feedback/stats": { ratings_count: 0, average_rating: null, testimonials_count: 1 },
  });
  renderApp(<Home />);
  expect(await screen.findByText(/Sample testimonials for preview/)).toBeInTheDocument();
  expect(screen.queryByText(/Real words from people/)).toBeNull();
  expect(screen.getByText(/Sample learner \(demo\)/)).toBeInTheDocument();
});

test("the landing page embeds the 30 second intro video with captions and a poster", async () => {
  mockApi({ "GET /testimonials/public": [], "GET /feedback/stats": { ratings_count: 0, average_rating: null, testimonials_count: 0 } });
  const { container } = renderApp(<Home />);
  expect(screen.getByRole("heading", { name: "See how AI Career Coach works" })).toBeInTheDocument();
  const video = container.querySelector("video") as HTMLVideoElement;
  expect(video).toHaveAttribute("controls");
  expect(video).not.toHaveAttribute("autoplay");
  expect(video.getAttribute("poster")).toBe("/video/ai-career-coach-intro-poster.jpg");
  expect(video.querySelector("source")?.getAttribute("src")).toBe("/video/ai-career-coach-intro-1080p.mp4");
  expect(video.querySelector("track")?.getAttribute("kind")).toBe("captions");
  expect(screen.getByRole("link", { name: "Download the 4K version" })).toHaveAttribute("href", "/video/ai-career-coach-intro-4k.mp4");
  await screen.findByText(/No testimonials have been published yet/);
});
