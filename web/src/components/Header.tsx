import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../api";
import { type ThemeMode, useTheme } from "../theme";
import { Logo } from "./Logo";
import { Button } from "./ui";

const NEXT: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };
const THEME_LABEL: Record<ThemeMode, string> = { system: "System", light: "Light", dark: "Dark" };

type Props = {
  q: string;
  onSearch: (q: string) => void;
  onMarkAllSeen?: () => void;
  markingSeen?: boolean;
  onAddCompany?: () => void;
};

export function Header({ q, onSearch, onMarkAllSeen, markingSeen, onAddCompany }: Props) {
  const [text, setText] = useState(q);
  const [theme, setTheme] = useTheme();
  const navigate = useNavigate();

  useEffect(() => setText(q), [q]);
  useEffect(() => {
    if (text === q) return;
    const t = setTimeout(() => onSearch(text), 300);
    return () => clearTimeout(t);
  }, [text, q, onSearch]);

  async function logout(everywhere = false) {
    if (everywhere && !window.confirm("Log out on every device, your phone included?")) return;
    const path = everywhere ? "/api/logout?everywhere=true" : "/api/logout";
    await api(path, { method: "POST" }).catch(() => undefined);
    navigate("/login");
  }

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1360px] flex-wrap items-center gap-3 px-4 py-3 lg:gap-4 lg:px-6">
        <Link to="/" className="flex shrink-0 items-center gap-2.5 text-ink no-underline">
          <Logo />
          <span className="text-base font-bold">Job Scraper</span>
        </Link>
        <div className="flex h-11 min-w-0 flex-[1_1_280px] items-center gap-2 rounded-[10px] border border-line bg-bg px-3 lg:h-10">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" className="shrink-0 text-muted">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <label htmlFor="q" className="sr-only">
            Search jobs
          </label>
          <input
            id="q"
            type="search"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Search title, company, skill…"
            className="h-full min-w-0 flex-1 border-0 bg-transparent text-ink outline-none placeholder:text-muted"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {onMarkAllSeen && (
            <Button onClick={onMarkAllSeen} disabled={markingSeen}>
              {markingSeen ? "Marking…" : "Mark all as seen"}
            </Button>
          )}
          {onAddCompany && (
            <Button primary onClick={onAddCompany}>
              Add company
            </Button>
          )}
          <Button
            onClick={() => setTheme(NEXT[theme])}
            aria-label={`Theme: ${THEME_LABEL[theme]}. Switch to ${THEME_LABEL[NEXT[theme]]}`}
            title={`Theme: ${THEME_LABEL[theme]}`}
            className="w-11 px-0 lg:w-10"
          >
            <ThemeIcon mode={theme} />
          </Button>
          <Button onClick={() => logout()} title="Log out of this browser">
            Log out
          </Button>
          <Button onClick={() => logout(true)} title="Log out on every device, phone included">
            Everywhere
          </Button>
        </div>
      </div>
    </header>
  );
}

function ThemeIcon({ mode }: { mode: ThemeMode }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 2,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
    className: "mx-auto",
  };
  if (mode === "light")
    return (
      <svg {...common}>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </svg>
    );
  if (mode === "dark")
    return (
      <svg {...common}>
        <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z" />
      </svg>
    );
  return (
    <svg {...common}>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" />
    </svg>
  );
}
