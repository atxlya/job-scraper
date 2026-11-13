import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api";
import type { Night, Run, SourceHealth } from "../types";
import { Sources } from "./Sources";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: vi.fn() }));
const mockApi = vi.mocked(api);

const nights: Night[] = Array.from({ length: 14 }, (_, i) => ({
  day: `2026-11-${String(i + 1).padStart(2, "0")}`,
  count: 40,
  status: "ok",
}));

function source(key: string, company: string, extra: Partial<SourceHealth> = {}): SourceHealth {
  return {
    key,
    company,
    adapter: "workday",
    origin: "registry",
    enabled: true,
    status: "ok",
    last_success_at: "2026-11-12T16:00:00Z",
    last_job_count: 40,
    last_error: null,
    consecutive_failures: 0,
    last_run: { kind: "incremental", status: "ok", started_at: "2026-11-12T16:00:00Z", duration_s: 120 },
    nights,
    ...extra,
  };
}

const rows: SourceHealth[] = [
  source("jpmorgan", "JPMorgan Chase", {
    status: "failing",
    consecutive_failures: 5,
    last_error: "robots.txt timed out",
    last_run: { kind: "incremental", status: "failed", started_at: "2026-11-12T16:00:00Z", duration_s: 31 },
  }),
  source("myntra", "Myntra", { status: "partial", last_error: "old error from last week" }),
  source("accenture", "Accenture"),
  source("adobe", "Adobe"),
  source("old", "Old Co", { enabled: false }),
];

const runs: Run[] = [
  {
    kind: "full",
    status: "ok",
    started_at: "2026-11-12T20:30:00Z",
    duration_s: 91 * 60,
    jobs_found: 19804,
    reported_total: 40112,
    new_count: 12,
    updated_count: 40,
    closed_count: 3,
    error: null,
  },
  {
    kind: "incremental",
    status: "failed",
    started_at: "2026-11-12T16:00:00Z",
    duration_s: 31,
    jobs_found: 0,
    reported_total: null,
    new_count: 0,
    updated_count: 0,
    closed_count: 0,
    error: "ParseError: site changed",
  },
];

function serve() {
  mockApi.mockImplementation(async (path: string) => {
    if (path === "/api/sources") return rows;
    if (path === "/api/schedule")
      return {
        incremental_minutes: 30,
        full_at: "02:00",
        tracked_at: "04:00",
        next_full_at: "2099-01-01T20:30:00Z",
        next_tracked_at: "2099-01-01T22:30:00Z",
      };
    if (path === "/api/sources/accenture/runs") return runs;
    return undefined;
  });
}

function laptop() {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query === "(min-width: 1024px)",
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

function show() {
  serve();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Sources />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  mockApi.mockReset();
});

it("sums up the sources on one line, with the next full sweep", async () => {
  show();
  const summary = await screen.findByTestId("summary");
  expect(summary).toHaveTextContent("2 OK · 1 partial · 1 failing · 1 off");
  await waitFor(() => expect(summary).toHaveTextContent("Next full sweep 02:00 IST"));
});

it("keeps the server's order: failing first", async () => {
  laptop();
  show();
  await screen.findByText("JPMorgan Chase");
  const names = screen.getAllByTestId("source-name").map((n) => n.textContent);
  expect(names).toEqual(["JPMorgan Chase", "Myntra", "Accenture", "Adobe", "Old Co"]);
});

it("shows status, failure streak, the last run and the error only while failing", async () => {
  laptop();
  show();
  const jpm = (await screen.findByText("JPMorgan Chase")).closest("tr")!;
  expect(jpm).toHaveTextContent("Failing · 5×");
  expect(jpm).toHaveTextContent("incremental · 31 s");
  expect(jpm).toHaveTextContent("robots.txt timed out");
  const myntra = screen.getByText("Myntra").closest("tr")!;
  expect(myntra).toHaveTextContent("Partial");
  expect(myntra).not.toHaveTextContent("old error from last week");
});

it("opens a source's last runs when its row is clicked, and closes them again", async () => {
  laptop();
  show();
  const row = (await screen.findByText("Accenture")).closest("tr")!;
  const toggle = within(row).getByRole("button", { name: /Accenture/ });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  const table = await screen.findByRole("table", { name: "Last runs of accenture" });
  const lines = within(table).getAllByRole("row").slice(1).map((r) => r.textContent);
  expect(lines[0]).toContain("full");
  expect(lines[0]).toContain("1 h 31 min");
  expect(lines[0]).toContain("19,804 / 40,112");
  expect(lines[1]).toContain("ParseError: site changed");
  await userEvent.click(toggle);
  expect(screen.queryByRole("table", { name: "Last runs of accenture" })).not.toBeInTheDocument();
});

it("on a phone, shows cards instead of a table, and a tap opens the runs", async () => {
  show();
  await screen.findByText("Accenture");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Accenture/ }));
  expect(await screen.findByRole("table", { name: "Last runs of accenture" })).toBeInTheDocument();
});
