import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
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
  place: "Bengaluru, India",
  country: "IN",
  more_places: 0,
  india: true,
  remote: false,
  posted_at: "2026-11-10T08:00:00Z",
  first_seen_at: "2026-11-10T08:00:00Z",
  is_new: true,
  eligibility: "ok",
  tag: null,
  stage: null,
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
  unchecked: null,
  tech_internship: true,
  sections: { about: "Build things", responsibilities: ["Write code"], requirements: [], preferred: [], eligibility: [] },
  description_html: null,
  has_description: true,
  note: null,
  changes: [],
  tag_history: [],
  steps: [],
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
      job = { ...job, tag: body.tag, stage: body.tag === "applied" ? job.stage : null };
      return job;
    }
    if (path.endsWith("/stage")) {
      const body = init.json as { stage: Detail["stage"] };
      job = { ...job, stage: body.stage };
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

function show(picked = true) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (seen: boolean) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <JobDetail id={7} picked={seen} />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const { rerender } = render(ui(picked));
  return (seen: boolean) => rerender(ui(seen));
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

it("a job opened for you doesn't fetch its description until you ask", async () => {
  serve({ has_description: false, sections: null });
  show(false);
  await userEvent.click(await screen.findByRole("button", { name: "Fetch description" }));
  expect(await screen.findByText("Fetched now")).toBeInTheDocument();
  expect(sent("/description")).toHaveLength(1);
  expect(sent("/seen")).toHaveLength(0);
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

it("doesn't mark the job seen when it was opened for you, only once you pick it", async () => {
  serve();
  const pick = show(false);
  expect(await screen.findByRole("heading", { name: base.title })).toBeInTheDocument();
  expect(sent("/seen")).toHaveLength(0);
  pick(true);
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

it.each([
  ["notice", "This is a notice: eligibility is in its PDF."],
  ["partial", "Only the title is known: open the posting to check."],
  ["snippet", "Only a search summary is available: open the posting to check."],
] as const)("says why Gemini never reads a %s job", async (unchecked, text) => {
  serve({ eligibility: "pending", unchecked });
  show();
  expect(await screen.findByText(text)).toBeInTheDocument();
});

it("a non-tech notice says eligibility is only checked for tech internships", async () => {
  serve({ eligibility: "pending", unchecked: "notice", tech_internship: false });
  show();
  expect(await screen.findByText("Eligibility is only checked for tech internships.")).toBeInTheDocument();
});


// --- stages after Applied ----------------------------------------------------------------

/** The tag buttons' Applied, not the stage picker's "Applied" step. */
async function appliedTag() {
  await screen.findByRole("group", { name: "Application stage" });
  return screen.getAllByRole("button", { name: "Applied" }).find((b) => !b.closest('[role="group"]'))!;
}

const applied: Partial<Detail> = {
  tag: "applied",
  stage: "oa",
  steps: [
    { stage: "applied", on: "2026-11-03", at: "2026-11-03T10:00:00Z", note: "via referral" },
    { stage: "oa", on: "2026-11-08", at: "2026-11-08T10:00:00Z", note: "HackerRank" },
  ],
  tag_history: [
    { at: "2026-11-03T10:00:00Z", from_tag: null, to_tag: "applied", from_stage: null, to_stage: null, event_date: "2026-11-03", note: "via referral" },
    { at: "2026-11-08T10:00:00Z", from_tag: "applied", to_tag: "applied", from_stage: null, to_stage: "oa", event_date: "2026-11-08", note: "HackerRank" },
  ],
};

it("shows no stage picker until the job is Applied", async () => {
  serve({ tag: "liked" });
  show();
  await screen.findByRole("button", { name: "Like" });
  expect(screen.queryByRole("group", { name: "Application stage" })).not.toBeInTheDocument();
});

it("an applied job shows its stage and a timeline, newest first", async () => {
  serve(applied);
  show();
  const stages = await screen.findByRole("group", { name: "Application stage" });
  expect(within(stages).getByRole("button", { name: "OA" })).toHaveAttribute("aria-pressed", "true");
  expect(within(stages).getByRole("button", { name: "Interview" })).toHaveAttribute("aria-pressed", "false");
  const steps = within(screen.getByRole("list", { name: "Application timeline" })).getAllByRole("listitem");
  expect(steps.map((li) => li.textContent)).toEqual([
    expect.stringMatching(/OA.*HackerRank.*8 Nov/),
    expect.stringMatching(/Applied.*via referral.*3 Nov/),
  ]);
});

it("picking a stage asks for its date and note, then saves it", async () => {
  serve(applied);
  show();
  const stages = await screen.findByRole("group", { name: "Application stage" });
  await userEvent.click(within(stages).getByRole("button", { name: "Interview" }));
  const date = screen.getByLabelText("Interview on") as HTMLInputElement;
  await userEvent.clear(date);
  await userEvent.type(date, "2026-11-12");
  await userEvent.type(screen.getByLabelText("Note (optional)"), "Round 1");
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(sent("/stage")).toHaveLength(1));
  expect(sent("/stage")[0].json).toEqual({ stage: "interview", event_date: "2026-11-12", note: "Round 1" });
  await waitFor(() => expect(within(stages).getByRole("button", { name: "Interview" })).toHaveAttribute("aria-pressed", "true"));
});

it("Rejected can be picked from any stage", async () => {
  serve({ ...applied, stage: null });
  show();
  const stages = await screen.findByRole("group", { name: "Application stage" });
  await userEvent.click(within(stages).getByRole("button", { name: "Rejected" }));
  await userEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() => expect(sent("/stage")).toHaveLength(1));
  expect(sent("/stage")[0].json).toMatchObject({ stage: "rejected" });
});

it("removing Applied from a job with a stage asks first", async () => {
  serve(applied);
  show();
  const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
  await userEvent.click(await appliedTag());
  expect(confirm).toHaveBeenLastCalledWith(expect.stringContaining("at OA"));
  expect(sent("/tag")).toHaveLength(0);
  await userEvent.click(await appliedTag());
  await waitFor(() => expect(sent("/tag")).toHaveLength(1));
  expect(sent("/tag")[0].json).toEqual({ tag: null });
  confirm.mockRestore();
});

it("Like and Dismiss on a job with a stage ask first too", async () => {
  serve(applied);
  show();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  await userEvent.click(await screen.findByRole("button", { name: "Like" }));
  await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(sent("/tag")).toEqual([]);
  expect(confirm).toHaveBeenCalledTimes(2);
  confirm.mockRestore();
});

it("Applied without a stage is removed without asking, as before", async () => {
  serve({ ...applied, stage: null });
  show();
  const confirm = vi.spyOn(window, "confirm");
  await userEvent.click(await appliedTag());
  await waitFor(() => expect(sent("/tag")).toHaveLength(1));
  expect(confirm).not.toHaveBeenCalled();
  confirm.mockRestore();
});

it("the change log names stage steps", async () => {
  serve(applied);
  show();
  expect(await screen.findByText(/OA \(8 Nov 2026\) — HackerRank/)).toBeInTheDocument();
});
