import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api";
import { useFilters } from "../filters";
import type { Stats } from "../types";
import { StatsStrip } from "./StatsStrip";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: vi.fn() }));
const mockApi = vi.mocked(api);

const stats: Stats = {
  new_today: 3,
  open_tech: 208,
  companies: 61,
  liked: 8,
  applied: 0,
  last_applied_at: null,
};

function Page() {
  const [f, set] = useFilters();
  const loc = useLocation();
  return (
    <>
      <StatsStrip f={f} set={set} />
      <div data-testid="query">{loc.search}</div>
    </>
  );
}

function show(at = "/") {
  mockApi.mockResolvedValue(stats);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[at]}>
        <Page />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => mockApi.mockReset());

const tile = (name: RegExp) => screen.getByRole("button", { name });

it("shows each number", async () => {
  show();
  expect(await screen.findByRole("button", { name: /New today\s*3/ })).toBeInTheDocument();
  expect(tile(/Open tech internships\s*208/)).toBeInTheDocument();
  expect(tile(/Liked\s*8/)).toBeInTheDocument();
  expect(tile(/Applied\s*0/)).toBeInTheDocument();
});

it.each([
  [/New today/, "?new=today"],
  [/Liked/, "?view=all&tag=liked"],
  [/Applied/, "?view=all&tag=applied"],
])("%s sets its filter in the URL and shows as active", async (name, query) => {
  show();
  await screen.findByRole("button", { name: /New today\s*3/ });
  await userEvent.click(tile(name));
  expect(screen.getByTestId("query")).toHaveTextContent(query);
  expect(tile(name)).toHaveAttribute("aria-pressed", "true");
  expect(tile(/Open tech internships/)).toHaveAttribute("aria-pressed", "false");
});

it("Open tech internships clears every filter, search included", async () => {
  show("/?company=google&tag=liked&q=ml");
  await screen.findByRole("button", { name: /New today\s*3/ });
  expect(tile(/Open tech internships/)).toHaveAttribute("aria-pressed", "false");
  await userEvent.click(tile(/Open tech internships/));
  expect(screen.getByTestId("query")).toHaveTextContent(/^$/);
  expect(tile(/Open tech internships/)).toHaveAttribute("aria-pressed", "true");
});

it("keeps the open job when a tile is clicked", async () => {
  show("/?job=5");
  await screen.findByRole("button", { name: /New today\s*3/ });
  await userEvent.click(tile(/Liked/));
  expect(screen.getByTestId("query")).toHaveTextContent("?view=all&tag=liked&job=5");
});

it("no tile is active once another filter is added", async () => {
  show("/?view=all&tag=liked&company=google");
  await screen.findByRole("button", { name: /New today\s*3/ });
  for (const b of screen.getAllByRole("button")) expect(b).toHaveAttribute("aria-pressed", "false");
});
