import { ApiError, request } from "../api/http";
import { useSession } from "../store/session";
import { mockApi, reset, type Call } from "./utils";

afterEach(reset);

test("turns the server error envelope into an ApiError without leaking anything else", async () => {
  mockApi({ "GET /x": () => ({ status: 422, body: { error: { code: "validation_error", message: "Invalid request", fields: [{ field: "email", message: "bad" }] } } }) });
  const err = (await request("/x").catch((e: unknown) => e)) as ApiError;
  expect(err).toBeInstanceOf(ApiError);
  expect(err).toMatchObject({ status: 422, code: "validation_error", message: "Invalid request" });
  expect(err.fields[0].field).toBe("email");
});

test("non-JSON failures still produce a safe generic message", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>boom</html>", { status: 502 })));
  const err = (await request("/x").catch((e: unknown) => e)) as ApiError;
  expect(err.message).toBe("Request failed (502)");
});

test("sends the access token, or the guest token, only where asked", async () => {
  useSession.setState({ accessToken: "ACCESS", guestToken: "GUEST" });
  const { calls } = mockApi({ "GET /a": {}, "GET /b": {}, "GET /c": {} });
  await request("/a");
  await request("/b", { auth: "guest" });
  await request("/c", { auth: "none" });
  expect(calls[0].headers.get("Authorization")).toBe("Bearer ACCESS");
  expect(calls[0].headers.get("X-Guest-Token")).toBeNull();
  expect(calls[1].headers.get("X-Guest-Token")).toBe("GUEST");
  expect(calls[1].headers.get("Authorization")).toBeNull();
  expect(calls[2].headers.get("Authorization")).toBeNull();
  expect(calls[2].headers.get("X-Guest-Token")).toBeNull();
});

test("a 401 triggers one refresh and a retry with the new token", async () => {
  useSession.setState({ accessToken: "OLD" });
  let first = true;
  const { calls } = mockApi({
    "GET /secret": (c: Call) => {
      if (first) { first = false; return { status: 401, body: { error: { code: "authentication_error", message: "no" } } }; }
      return { body: { ok: c.headers.get("Authorization") } };
    },
    "POST /auth/refresh": { access_token: "NEW" },
  });
  expect(await request("/secret")).toEqual({ ok: "Bearer NEW" });
  expect(calls.filter((c: Call) => c.path === "/auth/refresh")).toHaveLength(1);
  expect(useSession.getState().accessToken).toBe("NEW");
});

test("a failed refresh signs the user out instead of looping", async () => {
  useSession.setState({ accessToken: "OLD", user: { id: "1", email: "a@b.c", display_name: "A", role: "user" } });
  const denied = () => ({ status: 401, body: { error: { code: "authentication_error", message: "no" } } });
  const { calls } = mockApi({ "GET /secret": denied, "POST /auth/refresh": denied });
  await expect(request("/secret")).rejects.toMatchObject({ status: 401 });
  expect(useSession.getState().accessToken).toBeNull();
  expect(useSession.getState().user).toBeNull();
  expect(calls.map((c) => c.path)).toEqual(["/secret", "/auth/refresh"]);
});

test("tokens never reach localStorage; the guest token lives in sessionStorage only", () => {
  useSession.getState().setAuth("ACCESS");
  useSession.getState().setGuestToken("GUEST");
  expect(JSON.stringify({ ...localStorage })).not.toContain("ACCESS");
  expect(JSON.stringify({ ...localStorage })).not.toContain("GUEST");
  expect(sessionStorage.getItem("acc.guest")).toBe("GUEST");
});

test("204 responses resolve to undefined", async () => {
  mockApi({ "DELETE /x": () => ({ status: 204 }) });
  expect(await request("/x", { method: "DELETE" })).toBeUndefined();
});
