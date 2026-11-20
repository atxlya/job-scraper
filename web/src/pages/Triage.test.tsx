import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { todayIST } from "../format";
import type { JobCard, JobDetail, Tag } from "../types";
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
    stage: null,
    closed: false,
  };
}

const titles = ["First Intern", "Second Intern", "Third Intern"];
let tags: Record<number, Tag | null>;
let puts: { id: number; body: { tag: Tag | null; event_date?: string } }[];

function detail(c: JobCard): JobDetail {
  return {
    ...c,
    tag: tags[c.id] ?? null,
    external_id: String(c.id),
    locations: [c.location],
    employment_type: null,
    remote_type: null,
    url: `https://example.com/job/${c.id}`,
    apply_url: `https://example.com/job/${c.id}/apply`,
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
    steps: [],
  };
}

function serve() {
  tags = {};
  puts = [];
  const all = titles.map((t, i) => card(i + 1, t));
  mockApi.mockImplementation(async (path: string, init: { method?: string; json?: unknown } = {}) => {
    const tagMatch = path.match(/^\/api\/jobs\/(\d+)\/tag$/);
    if (tagMatch && init.method === "PUT") {
      const id = Number(tagMatch[1]);
      const body = init.json as { tag: Tag | null; event_date?: string };
      puts.push({ id, body });
      tags[id] = body.tag;
      return detail(all[id - 1]);
    }
    if (path.startsWith("/api/jobs?") || path === "/api/jobs") {
      const items = all.filter((c) => tags[c.id] !== "dismissed").map((c) => ({ ...c, tag: tags[c.id] ?? null }));
      return { total: items.length, items, loaded_at: "2026-11-12T00:00:00Z", max_id: 3 };
    }
    const one = path.match(/^\/api\/jobs\/(\d+)$/);
    if (one) return detail(all[Number(one[1]) - 1]);
    if (path === "/api/stats") return { new_today: 0, open_tech: 3, companies: 1, liked: 0, applied: 0, rejected: 0, last_applied_at: null };
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

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.search}</div>;
}

function show(at = "/") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[at]}>
        <Dashboard />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const heading = (name: string) => screen.findByRole("heading", { level: 2, name });
const press = (keys: string) => userEvent.keyboard(keys);

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  serve();
});

// The api mock is replaced in beforeEach, not reset here: the page unmounts after this
// (the note box saves on unmount) and still needs it.
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("keyboard, on a laptop", () => {
  beforeEach(laptop);

  it("j and k move between jobs; the detail panel and URL follow, and the card scrolls into view", async () => {
    show();
    await heading("First Intern");
    await press("j");
    expect(await heading("Second Intern")).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent("job=2");
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
    await press("j");
    expect(await heading("Third Intern")).toBeInTheDocument();
    await press("j"); // last one: stays
    expect(screen.getByTestId("where")).toHaveTextContent("job=3");
    await press("k");
    expect(await heading("Second Intern")).toBeInTheDocument();
  });

  it("l likes the open job, and l again removes it", async () => {
    show("/?job=1");
    await heading("First Intern");
    await press("l");
    await waitFor(() => expect(puts).toEqual([{ id: 1, body: { tag: "liked" } }]));
    await waitFor(() => expect(screen.getByRole("button", { name: "Like" })).toHaveAttribute("aria-pressed", "true"));
    await press("l");
    await waitFor(() => expect(puts[1]).toEqual({ id: 1, body: { tag: null } }));
  });

  it("keys pressed in quick succession act on the job the last key moved to", async () => {
    show();
    await heading("First Intern");
    act(() => {
      for (const key of ["j", "j", "l"]) window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
    });
    await waitFor(() => expect(puts).toEqual([{ id: 3, body: { tag: "liked" } }]));
  });

  it("a marks the open job applied, dated today", async () => {
    show("/?job=1");
    await heading("First Intern");
    await press("a");
    await waitFor(() => expect(puts).toEqual([{ id: 1, body: { tag: "applied", event_date: todayIST() } }]));
  });

  it("u removes the tag", async () => {
    show("/?job=1");
    await heading("First Intern");
    await press("l");
    await waitFor(() => expect(puts).toHaveLength(1));
    await press("u");
    await waitFor(() => expect(puts[1]).toEqual({ id: 1, body: { tag: null } }));
  });

  it("d dismisses the open job and moves to the next one, with an Undo toast", async () => {
    show("/?job=1");
    await heading("First Intern");
    await press("d");
    await waitFor(() => expect(puts).toEqual([{ id: 1, body: { tag: "dismissed" } }]));
    expect(await heading("Second Intern")).toBeInTheDocument();
    const toast = screen.getByRole("status");
    expect(toast).toHaveTextContent("Dismissed · First Intern");
    await userEvent.click(within(toast).getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(puts[1]).toEqual({ id: 1, body: { tag: null } }));
    expect(await heading("First Intern")).toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("z undoes the last dismiss too", async () => {
    show("/?job=2");
    await heading("Second Intern");
    await press("d");
    await waitFor(() => expect(puts).toHaveLength(1));
    await press("z");
    await waitFor(() => expect(puts[1]).toEqual({ id: 2, body: { tag: null } }));
  });

  it("o opens the apply link in a new tab", async () => {
    const open = vi.spyOn(window, "open").mockReturnValue(null);
    show("/?job=2");
    await heading("Second Intern");
    await press("o");
    expect(open).toHaveBeenCalledWith("https://example.com/job/2/apply", "_blank", "noopener,noreferrer");
  });

  it("/ focuses search, and Esc leaves it", async () => {
    show();
    await heading("First Intern");
    await press("/");
    const search = screen.getByRole("searchbox", { name: "Search jobs" });
    expect(search).toHaveFocus();
    expect(search).toHaveValue(""); // the slash isn't typed
    await press("{Escape}");
    expect(search).not.toHaveFocus();
  });

  it("Esc closes the open job", async () => {
    show("/?job=2");
    await heading("Second Intern");
    await press("{Escape}");
    expect(screen.getByTestId("where")).not.toHaveTextContent("job=");
  });

  it("? opens the list of shortcuts, and Esc closes it", async () => {
    show();
    await heading("First Intern");
    await press("?");
    const dialog = screen.getByRole("dialog", { name: "Keyboard shortcuts" });
    expect(dialog).toHaveTextContent("Dismiss and go to the next job");
    await press("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does nothing while you type in search or the note box", async () => {
    show("/?job=1");
    await heading("First Intern");
    await userEvent.type(screen.getByRole("searchbox", { name: "Search jobs" }), "jdl");
    await userEvent.type(screen.getByRole("textbox", { name: /note/i }), "jkdalou?");
    expect(puts).toEqual([]);
    expect(screen.getByTestId("where")).toHaveTextContent("job=1");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("ignores keys with Ctrl, Cmd or Alt", async () => {
    show("/?job=1");
    await heading("First Intern");
    await press("{Control>}l{/Control}{Meta>}d{/Meta}{Alt>}j{/Alt}");
    expect(puts).toEqual([]);
    expect(screen.getByTestId("where")).toHaveTextContent("job=1");
  });
});

describe("swipes, on a phone", () => {
  function swipe(el: Element, dx: number, dy = 0) {
    fireEvent.pointerDown(el, { pointerId: 1, clientX: 100, clientY: 100, isPrimary: true });
    for (let i = 1; i <= 5; i++) {
      fireEvent.pointerMove(el, { pointerId: 1, clientX: 100 + (dx * i) / 5, clientY: 100 + (dy * i) / 5 });
    }
    fireEvent.pointerUp(el, { pointerId: 1, clientX: 100 + dx, clientY: 100 + dy });
  }
  const cardOf = async (title: string) => (await screen.findByRole("link", { name: new RegExp(title) })).parentElement!;

  it("right likes the job and shows Undo for 5 seconds", async () => {
    show();
    swipe(await cardOf("First Intern"), 160);
    await waitFor(() => expect(puts).toEqual([{ id: 1, body: { tag: "liked" } }]));
    expect(screen.getByRole("status")).toHaveTextContent("Liked · First Intern");
  });

  it("left dismisses it; Undo puts it back", async () => {
    show();
    swipe(await cardOf("Second Intern"), -160);
    await waitFor(() => expect(puts).toEqual([{ id: 2, body: { tag: "dismissed" } }]));
    await waitFor(() => expect(screen.queryByRole("link", { name: /Second Intern/ })).not.toBeInTheDocument());
    await userEvent.click(within(screen.getByRole("status")).getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(puts[1]).toEqual({ id: 2, body: { tag: null } }));
    expect(await screen.findByRole("link", { name: /Second Intern/ })).toBeInTheDocument();
  });

  it("a short swipe springs back and does nothing", async () => {
    show();
    swipe(await cardOf("First Intern"), 40);
    await new Promise((r) => setTimeout(r, 20));
    expect(puts).toEqual([]);
  });

  it("a vertical drag scrolls, it doesn't swipe", async () => {
    show();
    swipe(await cardOf("First Intern"), 30, 200);
    await new Promise((r) => setTimeout(r, 20));
    expect(puts).toEqual([]);
  });

  it("a swipe doesn't also open the job", async () => {
    show();
    const el = await cardOf("First Intern");
    swipe(el, 160);
    fireEvent.click(screen.getByRole("link", { name: /First Intern/ }));
    expect(screen.getByTestId("where")).not.toHaveTextContent("job=");
  });

  it("the Undo toast goes away after 5 seconds", async () => {
    show();
    const el = await cardOf("First Intern");
    vi.useFakeTimers({ shouldAdvanceTime: true });
    swipe(el, 160);
    await waitFor(() => expect(screen.getByRole("status")).toBeInTheDocument());
    act(() => vi.advanceTimersByTime(5100));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("a job with a stage after Applied", () => {
  beforeEach(laptop);

  it("keys that would clear its stage do nothing and say why", async () => {
    tags[1] = "applied";
    const real = mockApi.getMockImplementation()!;
    mockApi.mockImplementation(async (path: string, init?: { method?: string; json?: unknown }) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const out = (await real(path, init as never)) as any;
      if (path === "/api/jobs/1") return { ...out, tag: "applied", stage: "interview" };
      if (path.startsWith("/api/jobs?") || path === "/api/jobs")
        return { ...out, items: out.items.map((c: JobCard) => (c.id === 1 ? { ...c, tag: "applied", stage: "interview" } : c)) };
      return out;
    });
    show();
    await heading("First Intern");
    for (const k of ["l", "a", "d", "u"]) await press(k);
    expect(puts).toEqual([]);
    expect(await screen.findByRole("status")).toHaveTextContent("At Interview: change it on the job page");
  });
});
