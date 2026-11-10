import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
import type { JobCard as Card } from "../types";
import { JobCard } from "./JobCard";

const base: Card = {
  id: 7,
  company: "Google",
  company_slug: "google",
  title: "Software Engineering Intern",
  location: "Bengaluru, India",
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
  ["pending", "Not checked"],
] as const)("eligibility %s reads %s", (eligibility, label) => {
  show({ eligibility });
  expect(screen.getByText(label)).toBeInTheDocument();
});

it("marks closed jobs and shows the tag", () => {
  show({ closed: true, tag: "applied" });
  expect(screen.getByText("Closed")).toBeInTheDocument();
  expect(screen.getByText("Applied")).toBeInTheDocument();
});

it("shows company, location and age", () => {
  show();
  expect(screen.getByRole("link")).toHaveTextContent("Google · Bengaluru, India · 2h ago");
});
