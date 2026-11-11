import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import { api } from "../api";
import { Header } from "./Header";

vi.mock("../api", async (orig) => ({ ...(await orig<typeof import("../api")>()), api: vi.fn() }));
const mockApi = vi.mocked(api);

it.each([
  ["Log out", "/api/logout"],
  ["Everywhere", "/api/logout?everywhere=true"],
])("%s logs out with %s", async (name, path) => {
  mockApi.mockReset();
  mockApi.mockResolvedValue(undefined);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(
    <MemoryRouter>
      <Header q="" onSearch={() => undefined} />
    </MemoryRouter>,
  );
  await userEvent.click(screen.getByRole("button", { name }));
  await waitFor(() => expect(mockApi).toHaveBeenCalledWith(path, { method: "POST" }));
});

it("Everywhere does nothing when the confirm is cancelled", async () => {
  mockApi.mockReset();
  vi.spyOn(window, "confirm").mockReturnValue(false);
  render(
    <MemoryRouter>
      <Header q="" onSearch={() => undefined} />
    </MemoryRouter>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Everywhere" }));
  expect(mockApi).not.toHaveBeenCalled();
});
