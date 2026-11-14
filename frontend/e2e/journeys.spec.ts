import { expect, test, type Page } from "@playwright/test";

const RESUME = `Jane Doe
Senior Python developer, 6 years of experience building REST APIs with FastAPI and PostgreSQL.
Skills: Python, SQL, Docker, Git, FastAPI, PostgreSQL.
Experience: Backend engineer at Acme Corp, 2019 to present. Education: BSc Computer Science.`;
const JD = `Backend Engineer. Requirements: Python, SQL, Docker, Kafka and Kubernetes. Preferred: AWS.
Responsibilities: design APIs, mentor juniors, own services. Minimum 4 years of experience.`;
const PASSWORD = "E2e-Learner-Passw0rd!";
const TESTIMONIAL = "The 15 day roadmap and mock interviews gave me a clear plan and real confidence.";

async function register(page: Page, email: string, name: string) {
  await page.goto("/register");
  await page.getByLabel("Display name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel(/^Password/).fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByRole("heading", { name: "Learning roadmaps" })).toBeVisible();
}

async function signInAdmin(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(process.env.E2E_ADMIN_EMAIL!);
  await page.getByLabel("Password").fill(process.env.E2E_ADMIN_PASSWORD!);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("link", { name: "Admin" }).click();
  await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible();
}

test("a guest can analyse a resume against a job description without signing in", async ({ page }) => {
  await page.goto("/analyze");
  await expect(page.getByText(/temporary guest session/i)).toBeVisible();
  await page.getByRole("tab", { name: "Match" }).click();
  await expect(page.getByRole("button", { name: "Run analysis" })).toBeDisabled();
  await page.getByLabel("Resume text").fill(RESUME);
  await page.getByLabel("Job description text").fill(JD);
  await page.getByRole("button", { name: "Run analysis" }).click();
  const score = page.getByLabel("Overall match score");
  await expect(score).toBeVisible();
  await expect(score).toHaveText(/\d+(\.\d+)?\/100/);
  await expect(page.getByText(/estimate/i).first()).toBeVisible();
  await expect(page.getByText(/Kafka/).first()).toBeVisible(); // a skill the resume lacks is reported as missing
});

test("visitors are sent to sign in before reaching account pages", async ({ page }) => {
  await page.goto("/learning");
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/login/);
});

test("an unknown certificate id is reported as not found", async ({ page }) => {
  await page.goto("/verify/ACC-AAAA-BBBB-CCCC");
  await expect(page.getByText(/No valid certificate was found/)).toBeVisible();
});

test("a registered user can create a 15-day roadmap, and the session survives a reload", async ({ page }) => {
  await register(page, "learner1@example.com", "Lena Learner");
  await expect(page.getByRole("radio")).toHaveCount(3);
  await page.getByLabel("Your goal").fill("Learn Python, SQL and Docker for backend roles");
  await page.getByLabel("15 days").check();
  await page.getByRole("button", { name: "Create roadmap" }).click();
  const link = page.getByRole("link", { name: /roadmap/i }).first();
  await expect(link).toBeVisible();
  await expect(page.getByText(/15 days/).first()).toBeVisible();
  await link.click();
  await expect(page.getByText(/Day 1/).first()).toBeVisible();
  // the refresh cookie restores the session without a new login
  await page.reload();
  await expect(page.getByText("Lena Learner")).toBeVisible();
});

test("testimonial: consent is explicit, moderation gates publication, withdrawal unpublishes", async ({ browser }) => {
  const user = await browser.newPage();
  await register(user, "learner2@example.com", "Omar Learner");
  await user.goto("/feedback");
  await expect(user.getByRole("checkbox", { name: /may be shown publicly/i })).not.toBeChecked();
  await user.getByLabel(/Your testimonial/).fill(TESTIMONIAL);
  await user.getByLabel(/Name to show publicly/).fill("Omar L.");
  await user.getByRole("checkbox", { name: /may be shown publicly/i }).check();
  await user.getByRole("button", { name: "Submit testimonial" }).click();
  await expect(user.getByText(/waiting for approval/)).toBeVisible();

  // not public before a moderator approves it
  const visitor = await browser.newPage();
  await visitor.goto("/testimonials");
  await expect(visitor.getByText(TESTIMONIAL)).toHaveCount(0);

  // the administrator approves it
  const admin = await browser.newPage();
  await signInAdmin(admin);
  await expect(admin.getByText(TESTIMONIAL)).toBeVisible();
  await admin.getByRole("button", { name: "approve" }).first().click();
  await expect(admin.getByText(TESTIMONIAL)).toHaveCount(0); // left the pending queue

  // now it is public and shows only the chosen display name
  await visitor.goto("/testimonials");
  await expect(visitor.getByText(TESTIMONIAL)).toBeVisible();
  await expect(visitor.getByText("Omar L.")).toBeVisible();
  await expect(visitor.getByText("learner2@example.com")).toHaveCount(0);

  // sharing offers exactly three platforms and posts nothing
  await user.goto("/feedback");
  const share = user.getByRole("link", { name: /^Share on / });
  await expect(share).toHaveText(["Share on LinkedIn", "Share on WhatsApp", "Share on Facebook"]);
  const [, wa, fb] = await share.evaluateAll((els) => els.map((e) => (e as HTMLAnchorElement).href));
  expect(new URL(wa).hostname).toBe("wa.me");
  expect(new URL(fb).hostname).toBe("www.facebook.com");

  // withdrawing consent removes it from the public wall immediately
  await user.getByRole("button", { name: "Withdraw public consent" }).click();
  await expect(user.getByText(/consent withdrawn/)).toBeVisible();
  await visitor.goto("/testimonials");
  await expect(visitor.getByText(TESTIMONIAL)).toHaveCount(0);
});

test("an ordinary user cannot open the admin console", async ({ page }) => {
  await register(page, "learner3@example.com", "Nia Learner");
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
  await page.goto("/admin");
  await expect(page.getByText("Administrator access is required.")).toBeVisible();
});
