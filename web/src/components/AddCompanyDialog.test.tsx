import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { AddCompanyDialog } from "./AddCompanyDialog";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: vi.fn() }));
const mockApi = vi.mocked(api);

const WORKDAY = "https://broadcom.wd1.myworkdayjobs.com/External_Career";

function serve(add: "ok" | "fail" = "ok") {
  mockApi.mockImplementation(async (path: string, init: { json?: unknown } = {}) => {
    const body = init.json as { url: string };
    if (path === "/api/sources/detect") {
      if (body.url.includes("oraclecloud")) {
        return { adapter: "oracle_hcm", config: { host: "egug.fa.us2.oraclecloud.com", site: "CX_1" }, key_hint: "egug" };
      }
      if (!body.url.includes("myworkdayjobs")) {
        throw new ApiError(422, "Not a Workday, Eightfold or Oracle HCM careers URL.");
      }
      return {
        adapter: "workday",
        config: { host: "broadcom.wd1.myworkdayjobs.com", tenant: "broadcom", site: "External_Career" },
        key_hint: "broadcom",
      };
    }
    if (path === "/api/sources") {
      await new Promise((r) => setTimeout(r, 50));
      if (add === "fail") throw new ApiError(422, "Test fetch failed: 0 jobs returned");
      return {
        key: "broadcom",
        jobs_found: 60,
        sample_titles: ["A", "B", "C", "D", "E"],
      };
    }
    throw new Error(`unexpected ${path}`);
  });
}

function show() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AddCompanyDialog open onClose={() => undefined} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockApi.mockReset();
});

it("detects the platform from a pasted URL and fills the name", async () => {
  serve();
  show();
  await userEvent.click(screen.getByLabelText("Careers page URL"));
  await userEvent.paste(WORKDAY);
  expect(await screen.findByText("Workday · tenant broadcom · site External_Career")).toBeInTheDocument();
  expect(screen.getByLabelText("Company name")).toHaveValue("Broadcom");
});

it("an unknown URL shows why and Save stays off", async () => {
  serve();
  show();
  await userEvent.type(screen.getByLabelText("Company name"), "Example");
  await userEvent.click(screen.getByLabelText("Careers page URL"));
  await userEvent.paste("https://example.com/jobs");
  expect(await screen.findByText(/Not a Workday, Eightfold or Oracle HCM/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Test and add" })).toBeDisabled();
});

it("tests the site, then shows what it found", async () => {
  serve();
  show();
  await userEvent.click(screen.getByLabelText("Careers page URL"));
  await userEvent.paste(WORKDAY);
  await screen.findByText(/Workday · tenant broadcom/);
  await userEvent.click(screen.getByRole("button", { name: "Test and add" }));
  expect(await screen.findByText("Testing…")).toBeInTheDocument();
  expect(await screen.findByText("Added — 60 jobs found")).toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(5);
  const add = mockApi.mock.calls.find(([p]) => p === "/api/sources");
  expect(add?.[1]).toMatchObject({ method: "POST", json: { company_name: "Broadcom", url: WORKDAY } });
});

it("a failed test fetch shows the problem and adds nothing", async () => {
  serve("fail");
  show();
  await userEvent.click(screen.getByLabelText("Careers page URL"));
  await userEvent.paste(WORKDAY);
  await screen.findByText(/Workday · tenant broadcom/);
  await userEvent.click(screen.getByRole("button", { name: "Test and add" }));
  expect(await screen.findByText("Test fetch failed: 0 jobs returned")).toBeInTheDocument();
  expect(screen.queryByText(/Added/)).not.toBeInTheDocument();
});

it("doesn't guess a name from an Oracle host", async () => {
  serve();
  show();
  await userEvent.click(screen.getByLabelText("Careers page URL"));
  await userEvent.paste("https://egug.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1");
  expect(await screen.findByText("Oracle HCM · egug.fa.us2.oraclecloud.com · site CX_1")).toBeInTheDocument();
  expect(screen.getByLabelText("Company name")).toHaveValue("");
});
