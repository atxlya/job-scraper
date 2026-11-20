import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../api";
import type { Application } from "../types";
import { Applications } from "./Applications";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: vi.fn() }));
const mockApi = vi.mocked(api);

const NOW = new Date("2026-11-12T06:30:00Z"); // 12:00 IST

function app(id: number, company: string, title: string, stage: Application["stage"], steps: [string, string][], closed = false): Application {
  return {
    id,
    company,
    company_slug: company.toLowerCase(),
    title,
    closed,
    stage,
    steps: steps.map(([s, on]) => ({ stage: s as Application["steps"][number]["stage"], on, at: `${on}T10:00:00Z`, note: null })),
    last_on: steps[steps.length - 1][1],
  };
}

const rows: Application[] = [
  app(1, "Google", "SWE Intern", "interview", [["applied", "2026-11-03"], ["oa", "2026-11-08"], ["interview", "2026-11-12"]]),
  app(2, "NVIDIA", "Deep Learning Intern", "offer", [["applied", "2026-10-20"], ["oa", "2026-10-25"], ["interview", "2026-11-02"], ["offer", "2026-11-10"]]),
  app(3, "Barclays", "Technology Summer Analyst", "interview", [["applied", "2026-10-28"], ["interview", "2026-11-06"]], true),
  app(4, "Intel", "Validation Intern", null, [["applied", "2026-11-11"]]),
  app(5, "Cisco", "Security Intern", "rejected", [["applied", "2026-10-01"], ["rejected", "2026-10-15"]], true),
];

function width(wide: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: wide && query === "(min-width: 1024px)",
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  }));
}

function show(data: Application[] = rows) {
  mockApi.mockImplementation(async (path: string) => (path === "/api/applications" ? data : undefined));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/applications"]}>
        <Applications />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("groups every applied job by stage, most advanced first, Rejected last", async () => {
  width(true);
  show();
  const groups = await screen.findAllByRole("region");
  expect(groups.map((g) => g.getAttribute("aria-label"))).toEqual(["Offer · 1", "Interview · 2", "Applied · 1", "Rejected · 1"]);
  expect(screen.getByText("5 applications · 1 offer · 2 interviewing · 1 rejected")).toBeInTheDocument();
});

it("on a laptop, each row shows the date of each step and the time since the last one", async () => {
  width(true);
  show();
  const interview = await screen.findByRole("region", { name: "Interview · 2" });
  const [google, barclays] = within(interview).getAllByRole("row").slice(1);
  expect(within(google).getAllByRole("cell").map((c) => c.textContent)).toEqual([
    "GoogleSWE Intern",
    "3 Nov",
    "8 Nov",
    "12 Nov",
    "Interview today",
  ]);
  expect(within(barclays).getAllByRole("cell")[2]).toHaveTextContent("—");
  expect(within(barclays).getByText("Closed")).toBeInTheDocument();
  const offer = screen.getByRole("region", { name: "Offer · 1" });
  expect(within(offer).getAllByRole("cell")[4]).toHaveTextContent("Offer 10 Nov · 2 days");
});

it("each job links to its page", async () => {
  width(true);
  show();
  expect(await screen.findByRole("link", { name: /SWE Intern/ })).toHaveAttribute("href", "/jobs/1");
});

it("on a phone, each job is a card with its steps in one line", async () => {
  width(false);
  show();
  const interview = await screen.findByRole("region", { name: "Interview · 2" });
  const first = within(interview).getAllByRole("link")[0];
  expect(first).toHaveTextContent("Applied 3 Nov · OA 8 Nov · Interview 12 Nov");
  expect(first).toHaveTextContent("Interview today");
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  const jump = screen.getByRole("navigation", { name: "Stages" });
  expect(within(jump).getAllByRole("link").map((a) => a.textContent)).toEqual(["Offer 1", "Interview 2", "Applied 1", "Rejected 1"]);
});

it("says what to do when there are no applications", async () => {
  width(true);
  show([]);
  expect(await screen.findByText(/No applications yet/)).toBeInTheDocument();
});

it("explains the rejected section is the rejection history", async () => {
  show();
  const rejected = await screen.findByRole("region", { name: "Rejected · 1" });
  expect(within(rejected).getByText(/Your rejection history, newest first/)).toBeInTheDocument();
});
