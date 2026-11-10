import { type FormEvent, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { api, ApiError } from "../api";
import { Logo } from "../components/Logo";

function safeNext(next: string | null): string {
  // Only same-site paths, never "//evil.com" or "https://…".
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export function Login() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [params] = useSearchParams();
  const navigate = useNavigate();

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/login", { method: "POST", json: { password } });
      navigate(safeNext(params.get("next")), { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Couldn't reach the server.");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-bg px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-xl border border-line bg-surface p-6 shadow-sm"
      >
        <div className="mb-6 flex items-center gap-3">
          <Logo />
          <h1 className="text-base font-bold">Job Scraper</h1>
        </div>
        <label htmlFor="password" className="mb-1.5 block text-[13px] font-semibold">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          autoFocus
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-11 w-full rounded-lg border border-line bg-surface px-3 text-ink outline-none focus:border-accent focus:ring-3 focus:ring-ring"
        />
        {error && (
          <p role="alert" className="mt-3 rounded-lg border border-warn-bd bg-warn-bg px-3 py-2 text-[13px] text-warn-fg">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || !password}
          className="mt-4 h-11 w-full rounded-lg bg-accent font-semibold text-on-accent hover:bg-accent-hover disabled:opacity-60"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
