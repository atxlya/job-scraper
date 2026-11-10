import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, setNavigate } from "./api";

function respond(status: number, body?: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status })),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("sends JSON and parses the reply", async () => {
    respond(200, { ok: true });
    expect(await api("/api/me", { method: "PUT", json: { a: 1 } })).toEqual({ ok: true });
    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(init.body).toBe('{"a":1}');
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("goes to login on 401, keeping where you were", async () => {
    const nav = vi.fn();
    setNavigate(nav);
    window.history.pushState({}, "", "/jobs/3");
    respond(401, { detail: "Not logged in" });
    await expect(api("/api/jobs/3")).rejects.toBeInstanceOf(ApiError);
    expect(nav).toHaveBeenCalledWith("/login?next=%2Fjobs%2F3");
  });

  it("throws the server's detail message", async () => {
    respond(422, { detail: "Not a Workday, Eightfold or Oracle HCM careers URL." });
    await expect(api("/api/sources/detect")).rejects.toMatchObject({
      status: 422,
      detail: "Not a Workday, Eightfold or Oracle HCM careers URL.",
    });
  });

  it("joins validation errors into one message", async () => {
    respond(422, { detail: [{ msg: "too long" }, { msg: "bad value" }] });
    await expect(api("/api/x")).rejects.toMatchObject({ detail: "too long; bad value" });
  });

  it("returns undefined for 204", async () => {
    respond(204);
    expect(await api("/api/jobs/1/seen", { method: "POST" })).toBeUndefined();
  });

  it("a 401 from login itself is an error, not a redirect", async () => {
    const nav = vi.fn();
    setNavigate(nav);
    respond(401, { detail: "Wrong password" });
    await expect(api("/api/login", { method: "POST" })).rejects.toMatchObject({
      detail: "Wrong password",
    });
    expect(nav).not.toHaveBeenCalled();
  });
});
