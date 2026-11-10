import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import type { JobDetail as Detail } from "../types";
import { JobDetail } from "./JobDetail";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: vi.fn() }));
const mockApi = vi.mocked(api);

const base: Detail = {
  id: 7,
  company: "Google",
  company_slug: "google",
  title: "Software Engineering Intern",
  location: "Bengaluru, India",
  posted_at: "2026-11-10T08:00:00Z",
  first_seen_at: "2026-11-10T08:00:00Z",
  is_new: true,
  eligibility: "ok",
  tag: null,
  closed: false,
  external_id: "123",
  locations: ["Bengaluru, India"],
  employment_type: "Intern",
  remote_type: null,
  url: "https://careers.google.com/jobs/123",
  apply_url: "https://careers.google.com/jobs/123/apply",
  degree: null,
  quote: null,
  checking: false,
  unclear: false,
  tech_internship: true,
  sections: { about: "Build things", responsibilities: ["Write code"], requirements: [], preferred: [], eligibility: [] },
  description_html: null,
  has_description: true,
  note: null,
  changes: [],
  tag_history: [],
};

type Call = { path: string; method: string; json?: unknown };
let calls: Call[];
let job: Detail;

function serve(overrides: Partial<Detail> = {}, failDescription?: ApiError) {
  job = { ...base, ...overrides };
  calls = [];
  mockApi.mockImplementation(async (path: string, init: { method?: string; json?: unknown } = {}) => {
    const method = init.method ?? "GET";
    calls.push({ path, method, json: init.json });
    if (path.endsWith("/tag")) {
      const body = init.json as { tag: Detail["tag"] };
      job = { ...job, tag: body.tag };
      return job;
    }
    if (path.endsWith("/description")) {
      if (failDescription) throw failDescription;
      job = { ...job, has_description: true, description_html: "<p>Fetched now</p>" };
      return job;
    }
    if (method === "GET") return job;
    return undefined;
  });
}

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <JobDetail id={7} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const sent = (suffix: string) => calls.filter((c) => c.path.endsWith(suffix));

beforeEach(() => {
  mockApi.mockReset();
});

it("Like sends liked, and clicking it again removes the tag", async () => {
  serve();
  show();
  await userEvent.click(await screen.findByRole("button", { name: "Like" }));
  await waitFor(() => expect(sent("/tag")).toHaveLength(1));
  expect(sent("/tag")[0].json).toEqual({ tag: "liked" });
  await waitFor(() => expect(screen.getByRole("button", { name: "Like" })).toHaveAttribute("aria-pressed", "true"));
  await userEvent.click(screen.getByRole("button", { name: "Like" }));
  await waitFor(() => expect(sent("/tag")).toHaveLength(2));
  expect(sent("/tag")[1].json).toEqual({ tag: null });
});

it("Applied asks for a date and note first", async () => {
  serve();
  show();
  await userEvent.click(await screen.findByRole("button", { name: "Applied" }));
  const date = screen.getByLabelText("Applied on") as HTMLInputElement;
  expect(date.value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  await userEvent.clear(date);
  await userEvent.type(date, "2026-11-12");
  await userEvent.type(screen.getByLabelText("Note (optional)"), "via referral");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(sent("/tag")).toHaveLength(1));
  expect(sent("/tag")[0].json).toEqual({ tag: "applied", event_date: "2026-11-12", note: "via referral" });
});

it("saves the note after typing stops", async () => {
  serve();
  show();
  await userEvent.type(await screen.findByLabelText("Note"), "OA on 14 Dec");
  expect(sent("/note")).toHaveLength(0);
  await waitFor(() => expect(sent("/note")).toHaveLength(1), { timeout: 2000 });
  expect(sent("/note")[0].json).toEqual({ note: "OA on 14 Dec" });
  expect(await screen.findByText("Saved")).toBeInTheDocument();
});

it("fetches a missing description once and shows it", async () => {
  serve({ has_description: false, sections: null });
  show();
  expect(await screen.findByText("Fetched now")).toBeInTheDocument();
  expect(sent("/description")).toHaveLength(1);
});

it("shows why a description couldn't be fetched", async () => {
  serve({ has_description: false, sections: null }, new ApiError(502, "Couldn't reach careers.google.com. Try again later."));
  show();
  expect(await screen.findByText(/Couldn't reach careers.google.com/)).toBeInTheDocument();
  expect(sent("/description")).toHaveLength(1);
});

it("eligibility box shows the degree line and the quote", async () => {
  serve({ eligibility: "warn", degree: "PhD", quote: "Must be enrolled at a US university." });
  show();
  expect(await screen.findByText("For PhD students only (from the title)")).toBeInTheDocument();
  expect(screen.getByText("“Must be enrolled at a US university.”")).toBeInTheDocument();
  expect(screen.getByText(/Check needed/)).toBeInTheDocument();
});

it("marks the job as seen when opened", async () => {
  serve();
  show();
  await waitFor(() => expect(sent("/seen")).toHaveLength(1));
});

it("links to apply and to the original posting", async () => {
  serve();
  show();
  expect(await screen.findByRole("link", { name: /Apply on Google/ })).toHaveAttribute("href", base.apply_url);
  expect(screen.getByRole("link", { name: /Original posting/ })).toHaveAttribute("href", base.url);
});

it("says eligibility isn't checked for other jobs", async () => {
  serve({ eligibility: "pending", tech_internship: false, sections: null, description_html: "<p>x</p>" });
  show();
  expect(await screen.findByText("Eligibility is only checked for tech internships.")).toBeInTheDocument();
});

it("saves a half-typed note when you switch to another job", async () => {
  serve();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { unmount } = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <JobDetail id={7} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  await userEvent.type(await screen.findByLabelText("Note"), "call back Fri");
  unmount(); // e.g. clicking the next job, well before the 800 ms save
  expect(sent("/note")).toHaveLength(1);
  expect(sent("/note")[0].json).toEqual({ note: "call back Fri" });
});
