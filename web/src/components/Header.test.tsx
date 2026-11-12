import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { Header } from "./Header";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: vi.fn() }));
const mockApi = vi.mocked(api);

/** jsdom has no matchMedia, so useMedia says "phone" unless a test turns laptop width on. */
function laptop() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(min-width: 1024px)",
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname}</div>;
}

function show(props: Partial<Parameters<typeof Header>[0]> = {}, at = "/") {
  render(
    <MemoryRouter initialEntries={[at]}>
      <Routes>
        <Route
          path="*"
          element={
            <>
              <Header q="" onSearch={() => undefined} {...props} />
              <Where />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  mockApi.mockReset();
});

describe("phone header", () => {
  it("shows only the logo, search and one ⋯ menu button", () => {
    show({ onAddCompany: () => undefined });
    expect(screen.getByRole("searchbox", { name: "Search jobs" })).toBeInTheDocument();
    expect(screen.getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? b.textContent)).toEqual([
      "More actions",
    ]);
  });

  it("the ⋯ menu holds every other action", async () => {
    show({ onAddCompany: () => undefined });
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    const items = screen.getAllByRole("menuitem").map((i) => i.textContent);
    expect(items).toEqual(["Add company", "Sources", "Theme: System", "Log out", "Log out everywhere…"]);
  });

  it("Add company calls its handler and closes the menu", async () => {
    const onAdd = vi.fn();
    show({ onAddCompany: onAdd });
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Add company" }));
    expect(onAdd).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("Sources goes to the sources page, and isn't offered there", async () => {
    show();
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Sources" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/sources");
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.queryByRole("menuitem", { name: "Sources" })).not.toBeInTheDocument();
  });

  it("Theme cycles and keeps the menu open", async () => {
    show();
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Theme: System" }));
    expect(screen.getByRole("menuitem", { name: "Theme: Light" })).toBeInTheDocument();
  });

  it("Escape closes the menu and puts focus back on its button", async () => {
    show();
    const button = screen.getByRole("button", { name: "More actions" });
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  it("a click outside closes the menu", async () => {
    show();
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    await userEvent.click(screen.getByTestId("where"));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("arrow keys move between items", async () => {
    show({ onAddCompany: () => undefined });
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    expect(screen.getByRole("menuitem", { name: "Add company" })).toHaveFocus();
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getByRole("menuitem", { name: "Sources" })).toHaveFocus();
    await userEvent.keyboard("{ArrowUp}{ArrowUp}");
    expect(screen.getByRole("menuitem", { name: "Log out everywhere…" })).toHaveFocus();
  });
});

describe("laptop header", () => {
  it("has search, Add company, theme and an Account menu, and nothing else", () => {
    laptop();
    show({ onAddCompany: () => undefined });
    expect(screen.getByRole("button", { name: "Add company" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Theme: / })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Account" })).toBeInTheDocument();
    expect(screen.getAllByRole("button")).toHaveLength(3);
  });

  it("the Account menu holds the two log-outs", async () => {
    laptop();
    show();
    await userEvent.click(screen.getByRole("button", { name: "Account" }));
    expect(screen.getAllByRole("menuitem").map((i) => i.textContent)).toEqual([
      "Log out",
      "Log out everywhere…",
    ]);
  });
});

describe("logging out", () => {
  it.each([
    ["Log out", "/api/logout"],
    ["Log out everywhere…", "/api/logout?everywhere=true"],
  ])("%s calls %s and goes to the login page", async (name, path) => {
    mockApi.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    show();
    await userEvent.click(screen.getByRole("button", { name: "More actions" }));
    await userEvent.click(screen.getByRole("menuitem", { name }));
    await waitFor(() => expect(mockApi).toHaveBeenCalledWith(path, { method: "POST" }));
    await waitFor(() => expect(screen.getByTestId("where")).toHaveTextContent("/login"));
  });

  it("Log out everywhere asks first, and does nothing when cancelled", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    laptop();
    show();
    await userEvent.click(screen.getByRole("button", { name: "Account" }));
    await userEvent.click(screen.getByRole("menuitem", { name: "Log out everywhere…" }));
    expect(confirm).toHaveBeenCalledOnce();
    expect(mockApi).not.toHaveBeenCalled();
  });
});
