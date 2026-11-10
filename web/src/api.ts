/** Fetch wrapper for the dashboard API. JSON in and out; a 401 sends you to the login page. */

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail);
  }
}

let navigate: (to: string) => void = (to) => window.location.assign(to);

/** Lets the router take over the 401 redirect (and tests observe it). */
export function setNavigate(fn: (to: string) => void) {
  navigate = fn;
}

type Init = Omit<RequestInit, "body"> & { json?: unknown };

export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const { json, ...rest } = init;
  const headers = new Headers(rest.headers);
  let body: BodyInit | undefined;
  if (json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }
  const res = await fetch(path, { ...rest, headers, body, credentials: "same-origin" });
  if (res.status === 401 && !path.startsWith("/api/login")) {
    const here = window.location.pathname + window.location.search;
    navigate(`/login?next=${encodeURIComponent(here)}`);
    throw new ApiError(401, "Not logged in");
  }
  if (!res.ok) throw new ApiError(res.status, await detailOf(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function detailOf(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail.map((d: { msg?: string }) => d.msg ?? "invalid").join("; ");
    }
  } catch {
    // not JSON
  }
  return res.statusText || `HTTP ${res.status}`;
}
