import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import type { Schedule } from "../types";
import { ScheduleCard } from "./ScheduleCard";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: vi.fn() }));
const mockApi = vi.mocked(api);

const saved: Schedule = {
  incremental_minutes: 30,
  full_at: "02:00",
  tracked_at: "04:00",
  next_full_at: "2099-01-01T20:30:00Z",
  next_tracked_at: "2099-01-01T22:30:00Z",
};

function show(put: (body: unknown) => Schedule | Promise<Schedule> = (b) => ({ ...saved, ...(b as object) })) {
  mockApi.mockImplementation(async (path: string, init?: { method?: string; json?: unknown }) => {
    if (path === "/api/schedule" && init?.method === "PUT") return put(init.json);
    if (path === "/api/schedule") return saved;
    return undefined;
  });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ScheduleCard />
    </QueryClientProvider>,
  );
}

afterEach(() => mockApi.mockReset());

it("shows the current schedule", async () => {
  show();
  const line = await screen.findByTestId("schedule");
  expect(line).toHaveTextContent("Quick check every 30 min");
  expect(line).toHaveTextContent("Full sweep 02:00 IST");
  expect(line).toHaveTextContent("Re-check tracked jobs 04:00 IST");
});

it("saves a new schedule", async () => {
  const user = userEvent.setup();
  show();
  await user.click(await screen.findByRole("button", { name: "Edit schedule" }));
  const every = screen.getByLabelText("Quick check every (minutes)");
  await user.clear(every);
  await user.type(every, "45");
  const full = screen.getByLabelText("Full sweep at (IST)");
  await user.clear(full);
  await user.type(full, "01:30");
  await user.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(mockApi).toHaveBeenCalledWith("/api/schedule", {
      method: "PUT",
      json: { incremental_minutes: 45, full_at: "01:30", tracked_at: "04:00" },
    }),
  );
  expect(await screen.findByTestId("schedule")).toHaveTextContent("Quick check every 45 min");
  expect(screen.getByTestId("schedule")).toHaveTextContent("Full sweep 01:30 IST");
  expect(screen.getByRole("status")).toHaveTextContent("Saved. The worker switches within a minute.");
});

it("shows why a schedule was refused, and keeps the form open", async () => {
  const user = userEvent.setup();
  show(() => {
    throw new ApiError(422, "The quick check must be at least 15 min apart.");
  });
  await user.click(await screen.findByRole("button", { name: "Edit schedule" }));
  const every = screen.getByLabelText("Quick check every (minutes)");
  await user.clear(every);
  await user.type(every, "5");
  await user.click(screen.getByRole("button", { name: "Save" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("at least 15 min apart");
  expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
});

it("cancel leaves the schedule as it was", async () => {
  const user = userEvent.setup();
  show();
  await user.click(await screen.findByRole("button", { name: "Edit schedule" }));
  await user.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByTestId("schedule")).toHaveTextContent("Quick check every 30 min");
  expect(mockApi).not.toHaveBeenCalledWith("/api/schedule", expect.objectContaining({ method: "PUT" }));
});
