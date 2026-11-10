import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { Login } from "./Login";

function Where() {
  return <p data-testid="where">{useLocation().pathname}</p>;
}

function renderAt(url: string) {
  render(
    <MemoryRouter initialEntries={[url]}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => vi.unstubAllGlobals());

async function signIn(status: number, detail?: string) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(detail ? JSON.stringify({ detail }) : null, { status })),
  );
  await userEvent.type(screen.getByLabelText("Password"), "pw");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

it("goes to the page you came from", async () => {
  renderAt("/login?next=%2Fjobs%2F3");
  await signIn(204);
  expect(await screen.findByTestId("where")).toHaveTextContent("/jobs/3");
});

it("never redirects off-site", async () => {
  renderAt("/login?next=%2F%2Fevil.example");
  await signIn(204);
  expect(await screen.findByTestId("where")).toHaveTextContent(/^\/$/);
});

it("shows the server's message", async () => {
  renderAt("/login");
  await signIn(503, "No dashboard password is set. Run: python -m app.cli set-password");
  expect(await screen.findByRole("alert")).toHaveTextContent("set-password");
});
