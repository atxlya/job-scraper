import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import type { Night } from "../types";
import { NightsChart } from "./NightsChart";

const night = (day: string, count: number | null, status: Night["status"] = count === null ? null : "ok"): Night => ({
  day,
  count,
  status,
});

const nights: Night[] = [
  night("2026-11-08", null),
  night("2026-11-09", 40),
  night("2026-11-10", 30, "failed"),
  night("2026-11-11", 20),
];

it("says what it shows, for screen readers", () => {
  render(<NightsChart nights={nights} />);
  expect(screen.getByRole("img")).toHaveAccessibleName(
    "Jobs read by the nightly full sweep: 9 Nov 40, 10 Nov failed, 11 Nov 20",
  );
});

it("draws a line through ok nights only, skipping gaps and failures", () => {
  const { container } = render(<NightsChart nights={nights} />);
  const lines = container.querySelectorAll("polyline");
  expect(lines).toHaveLength(2); // 9 Nov on its own, then 11 Nov: the failed night breaks the line
  expect(container.querySelectorAll("circle[data-failed]")).toHaveLength(1);
});

it("puts the line on a zero baseline, so a halving looks like one", () => {
  const { container } = render(<NightsChart nights={[night("a", 40), night("b", 20)]} />);
  const [y40, y20] = container.querySelector("polyline")!.getAttribute("points")!.split(" ").map((p) => Number(p.split(",")[1]));
  const base = 31;
  expect((base - y20) / (base - y40)).toBeCloseTo(0.5, 1);
});

it("shows the night's date and number on hover", async () => {
  render(<NightsChart nights={nights} />);
  await userEvent.hover(screen.getAllByTestId("night")[3]);
  expect(screen.getByRole("tooltip")).toHaveTextContent("11 Nov · 20 jobs");
  await userEvent.hover(screen.getAllByTestId("night")[2]);
  expect(screen.getByRole("tooltip")).toHaveTextContent("10 Nov · failed");
  await userEvent.hover(screen.getAllByTestId("night")[0]);
  expect(screen.getByRole("tooltip")).toHaveTextContent("8 Nov · no full sweep");
});

it("says so when there are no full sweeps yet", () => {
  render(<NightsChart nights={[night("2026-11-11", null)]} />);
  expect(screen.getByText("No full sweep yet")).toBeInTheDocument();
});
