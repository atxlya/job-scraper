import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../api";
import type { JobCard, JobDetail } from "../types";
import { Dashboard } from "./Dashboard";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: vi.fn() }));
const mockApi = vi.mocked(api);

function card(id: number, title: string): JobCard {
  return {
    id,
    company: "Google",
    company_slug: "google",
    title,
    location: "Bengaluru, India",
    place: "Bengaluru, India",
    country: "IN",
    more_places: 0,
    india: true,
    remote: false,
    posted_at: "2026-11-10T08:00:00Z",
    first_seen_at: "2026-11-10T08:00:00Z",
    is_new: true,
    eligibility: "pending",
    tag: null,
    closed: false,
  };
}

const cards = [card(1, "First Intern"), card(2, "Second Intern")];

function detail(c: JobCard): JobDetail {
  return {
    ...c,
    external_id: String(c.id),
    locations: [c.location],
    employment_type: null,
    remote_type: null,
    url: "https://example.com/job",
    apply_url: null,
    degree: null,
    quote: null,
    checking: false,
    unclear: false,
    unchecked: null,
    tech_internship: true,
    sections: null,
    description_html: "<p>x</p>",
    has_description: true,
    note: null,
    changes: [],
    tag_history: [],
  };
}

let paths: string[];

function serve(items: JobCard[] = cards) {
  paths = [];
  mockApi.mockImplementation(async (path: string, init: { method?: string } = {}) => {
    paths.push(`${init.method ?? "GET"} ${path}`);
    if (path.startsWith("/api/jobs?") || path === "/api/jobs") {
      return { total: items.length, items, loaded_at: "2026-11-12T00:00:00Z", max_id: 2 };
    }
    const one = path.match(/^\/api\/jobs\/(\d+)$/);
    if (one) return detail(cards.find((c) => c.id === Number(one[1]))!);
    if (path === "/api/stats") return { new_today: 0, open_tech: 2, companies: 1, liked: 0, applied: 0, last_applied_at: null };
    if (path.startsWith("/api/filters")) return { companies: [], countries: [] };
    if (path === "/api/sources") return [];
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

function show(at = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[at]}>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  mockApi.mockReset();
});

const seenCalls = () => paths.filter((p) => p.startsWith("POST") && p.endsWith("/seen"));

it("on a laptop, opens the first job when none is picked, without marking it seen", async () => {
  laptop();
  serve();
  show();
  expect(await screen.findByRole("heading", { level: 2, name: "First Intern" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /First Intern/ })).toHaveAttribute("aria-current", "true");
  expect(screen.queryByText("Pick a job to see its details here.")).not.toBeInTheDocument();
  await new Promise((r) => setTimeout(r, 20));
  expect(seenCalls()).toEqual([]);
});

it("marks it seen once you click it", async () => {
  laptop();
  serve();
  show();
  await screen.findByRole("heading", { level: 2, name: "First Intern" });
  await userEvent.click(screen.getByRole("link", { name: /First Intern/ }));
  await waitFor(() => expect(seenCalls()).toEqual(["POST /api/jobs/1/seen"]));
});

it("a picked job wins over the first one", async () => {
  laptop();
  serve();
  show("/?job=2");
  expect(await screen.findByRole("heading", { level: 2, name: "Second Intern" })).toBeInTheDocument();
  await waitFor(() => expect(seenCalls()).toEqual(["POST /api/jobs/2/seen"]));
});

it("with no jobs, the details side says so", async () => {
  laptop();
  serve([]);
  show();
  expect(await screen.findByText("No jobs match these filters.")).toBeInTheDocument();
  expect(screen.getByText("Pick a job to see its details here.")).toBeInTheDocument();
});

it("on a phone, nothing opens by itself", async () => {
  serve();
  show();
  expect(await screen.findByRole("link", { name: /First Intern/ })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
  expect(paths.some((p) => p === "GET /api/jobs/1")).toBe(false);
});
