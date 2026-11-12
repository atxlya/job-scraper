import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import { JobList } from "./JobList";

function show(props: Partial<Parameters<typeof JobList>[0]> = {}) {
  render(
    <MemoryRouter>
      <JobList
        title="Tech internships"
        pages={{ pages: [{ total: 0, items: [], loaded_at: "2026-11-12T00:00:00Z", max_id: 0 }], pageParams: [0] }}
        loading={false}
        error={null}
        hasMore={false}
        loadingMore={false}
        onMore={() => undefined}
        linkFor={(id) => `/jobs/${id}`}
        selected={null}
        onClear={() => undefined}
        {...props}
      />
    </MemoryRouter>,
  );
}

it("has Mark all as seen in the list's own header row", async () => {
  const onMark = vi.fn();
  show({ onMarkAllSeen: onMark });
  const heading = screen.getByRole("heading", { name: "Tech internships" });
  const row = heading.parentElement!.parentElement!;
  const button = screen.getByRole("button", { name: "Mark all as seen" });
  expect(row).toContainElement(button);
  await userEvent.click(button);
  expect(onMark).toHaveBeenCalledOnce();
});

it("shows Marking… and is disabled while marking", () => {
  show({ onMarkAllSeen: () => undefined, markingSeen: true });
  expect(screen.getByRole("button", { name: "Marking…" })).toBeDisabled();
});

it("puts an extra control, such as the phone's Filters button, next to the title", () => {
  show({ aside: <button type="button">Filters (2)</button> });
  expect(screen.getByRole("button", { name: "Filters (2)" })).toBeInTheDocument();
});

it("has an Export CSV link in the same row, which downloads", () => {
  show({
    exportHref: "/api/jobs.csv?company=google",
    onMarkAllSeen: () => undefined,
    pages: { pages: [{ total: 3, items: [], loaded_at: "2026-11-12T00:00:00Z", max_id: 3 }], pageParams: [0] },
  });
  const link = screen.getByRole("link", { name: "Export CSV" });
  expect(link).toHaveAttribute("href", "/api/jobs.csv?company=google");
  expect(link).toHaveAttribute("download");
  const row = screen.getByRole("button", { name: "Mark all as seen" }).parentElement!;
  expect(row).toContainElement(link);
});

it("has no Export CSV link while the list is empty", () => {
  show({ exportHref: "/api/jobs.csv" });
  expect(screen.queryByRole("link", { name: "Export CSV" })).not.toBeInTheDocument();
});
