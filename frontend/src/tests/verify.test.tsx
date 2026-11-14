import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { Verify } from "../pages/Certificates";
import { mockApi, renderApp, reset, signIn } from "./utils";

afterEach(reset);

const page = (
  <Routes>
    <Route path="/verify" element={<Verify />} />
    <Route path="/verify/:id" element={<Verify />} />
  </Routes>
);

test("the verify page shows three clearly labelled sample certificates", () => {
  mockApi({});
  renderApp(page, "/verify");
  const images = screen.getAllByRole("img");
  expect(images).toHaveLength(3);
  for (const img of images) {
    expect(img.getAttribute("alt")).toMatch(/^Sample .* certificate \(not a real certificate\)$/);
    expect(img.getAttribute("src")).toMatch(/^\/samples\/certificate-.*\.png$/);
  }
  expect(screen.getByText(/cannot be verified/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "What you can earn" })).toBeInTheDocument();
});

test("visitors are invited to register; signed-in users are sent to their certificates", () => {
  mockApi({});
  const first = renderApp(page, "/verify");
  expect(screen.getByRole("link", { name: "Register and start earning yours" })).toHaveAttribute("href", "/register");
  first.unmount();
  signIn();
  renderApp(page, "/verify");
  expect(screen.getByRole("link", { name: "See what I can claim" })).toHaveAttribute("href", "/certificates");
});

test("a sample certificate ID does not verify, and the samples stay visible", async () => {
  mockApi({ "GET /certificates/verify/SAMPLE-NOT-VALID-1": () => ({ status: 404, body: { error: { code: "not_found", message: "Not Found" } } }) });
  renderApp(page, "/verify/SAMPLE-NOT-VALID-1");
  expect(await screen.findByText(/No valid certificate was found/)).toBeInTheDocument();
  expect(screen.getAllByRole("img")).toHaveLength(3);
});
