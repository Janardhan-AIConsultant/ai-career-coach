afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

async function load(base: string) {
  vi.stubEnv("VITE_API_BASE_URL", base);
  vi.resetModules();
  return import("../api/http");
}

test("a same-origin base (production behind a Vercel rewrite) produces relative /api/v1 URLs", async () => {
  const http = await load("/");
  expect(http.API_ROOT).toBe("/api/v1");
  const fetchMock = vi.fn(async (_input: RequestInfo | URL) => new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  await http.request("/health", { auth: "none" });
  expect(String(fetchMock.mock.calls[0][0])).toBe(`${window.location.origin}/api/v1/health`);
});

test("an absolute base keeps its host and drops trailing slashes", async () => {
  const http = await load("https://api.example.com/");
  expect(http.API_ROOT).toBe("https://api.example.com/api/v1");
});
