import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import type { JobCard as Card } from "../types";
import { JobCard } from "./JobCard";

vi.mock("../logos", () => ({ logoFor: (slug: string) => (slug === "intel" ? "/assets/intel.svg" : null) }));

const base: Card = {
  id: 7,
  company: "Google",
  company_slug: "google",
  title: "Software Engineering Intern",
  location: "Bengaluru, Karnataka, India",
  place: "Bengaluru, India",
  country: "IN",
  more_places: 0,
  india: true,
  remote: false,
  posted_at: "2026-11-10T08:00:00Z",
  first_seen_at: "2026-11-10T08:00:00Z",
  is_new: false,
  eligibility: "ok",
  tag: null,
  closed: false,
};

function show(job: Partial<Card> = {}, to = "/?job=7") {
  render(
    <MemoryRouter>
      <JobCard job={{ ...base, ...job }} to={to} selected={false} now={new Date("2026-11-10T10:00:00Z")} />
    </MemoryRouter>,
  );
}

it("is a link to the job", () => {
  show({}, "/jobs/7");
  expect(screen.getByRole("link")).toHaveAttribute("href", "/jobs/7");
});

it("shows NEW only for new jobs", () => {
  show({ is_new: true });
  expect(screen.getByText("NEW")).toBeInTheDocument();
});

it("hides NEW for seen jobs", () => {
  show();
  expect(screen.queryByText("NEW")).not.toBeInTheDocument();
});

it.each([
  ["ok", "Eligible"],
  ["warn", "Check needed"],
] as const)("eligibility %s shows a %s badge", (eligibility, label) => {
  show({ eligibility });
  expect(screen.getByText(label)).toBeInTheDocument();
});

it("shows no eligibility badge while a job isn't checked yet", () => {
  show({ eligibility: "pending" });
  for (const label of ["Not checked", "Eligible", "Check needed"])
    expect(screen.queryByText(label)).not.toBeInTheDocument();
});

it("marks closed jobs and shows the tag", () => {
  show({ closed: true, tag: "applied" });
  expect(screen.getByText("Closed")).toBeInTheDocument();
  expect(screen.getByText("Applied")).toBeInTheDocument();
});

it("shows company, flag and City, Country, and age", () => {
  show({ india: false });
  expect(screen.getByRole("link")).toHaveTextContent("Google · 🇮🇳 Bengaluru, India · 2h ago");
});

it("counts the other locations, and keeps the full list as a tooltip", () => {
  show({ more_places: 2, location: "Bengaluru, India · Pune, India +1" });
  expect(screen.getByText("+2")).toBeInTheDocument();
  expect(screen.getByTitle("Bengaluru, India · Pune, India +1")).toBeInTheDocument();
});

it("marks India and remote jobs", () => {
  show({ india: true, remote: true });
  expect(screen.getByText("India")).toBeInTheDocument();
  expect(screen.getByText("Remote")).toBeInTheDocument();
});

it("shows neither mark otherwise", () => {
  show({ india: false, remote: false });
  expect(screen.queryByText("India")).not.toBeInTheDocument();
  expect(screen.queryByText("Remote")).not.toBeInTheDocument();
});

it("has no flag when the country is unknown", () => {
  show({ country: null, place: "Belen", india: false });
  expect(screen.getByRole("link")).toHaveTextContent("Google · Belen · 2h ago");
});

it("uses the company's logo when there is one", () => {
  show({ company: "Intel", company_slug: "intel" });
  expect(screen.getByRole("link").querySelector("img")).toHaveAttribute("src", "/assets/intel.svg");
});

it("otherwise shows initials on the company's own color", () => {
  show();
  const icon = screen.getByText("G");
  expect(icon.style.getPropertyValue("--hue")).toMatch(/^\d+$/);
});
