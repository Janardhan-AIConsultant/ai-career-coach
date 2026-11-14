import { FEEDBACK_FEATURES, PLATFORM_LABEL, ROADMAP_DURATIONS, SHARE_PLATFORMS } from "../lib/constants";

test("only 7, 15 and 60 day roadmaps are offered", () => {
  expect([...ROADMAP_DURATIONS]).toEqual([7, 15, 60]);
});

test("only LinkedIn, WhatsApp and Facebook are share platforms", () => {
  expect([...SHARE_PLATFORMS]).toEqual(["linkedin", "whatsapp", "facebook"]);
  expect(Object.values(PLATFORM_LABEL)).toEqual(["LinkedIn", "WhatsApp", "Facebook"]);
});

test("feedback features match the server's closed set", () => {
  expect(Object.keys(FEEDBACK_FEATURES)).toHaveLength(8);
});
