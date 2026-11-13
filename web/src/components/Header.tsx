import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { api } from "../api";
import { useMedia, WIDE } from "../hooks";
import { type ThemeMode, useTheme } from "../theme";
import { Logo } from "./Logo";
import { Menu, MenuItem, MenuSeparator } from "./Menu";
import { Button } from "./ui";

const NEXT: Record<ThemeMode, ThemeMode> = { system: "light", light: "dark", dark: "system" };
const THEME_LABEL: Record<ThemeMode, string> = { system: "System", light: "Light", dark: "Dark" };
const square = "h-11 w-11 rounded-[10px] border border-line bg-surface text-ink hover:bg-chip lg:h-10 lg:w-10";
const NAV = [
  ["/applications", "Applications"],
  ["/sources", "Sources"],
] as const;

type Props = {
  q: string;
  onSearch: (q: string) => void;
  onAddCompany?: () => void;
};

/** Phone: logo, search and one ⋯ menu. Laptop: search, Applications, Sources, Add company, theme and an Account menu. */
export function Header({ q, onSearch, onAddCompany }: Props) {
  const [text, setText] = useState(q);
  const [theme, setTheme] = useTheme();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const wide = useMedia(WIDE);

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

  const logouts = (
    <>
      <MenuItem onSelect={() => logout()}>Log out</MenuItem>
      <MenuItem danger onSelect={() => logout(true)}>
        Log out everywhere…
      </MenuItem>
    </>
  );

  return (
    <header className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-[1360px] items-center gap-2 px-4 py-2.5 lg:gap-4 lg:px-6 lg:py-3">
        <Link to="/" className="flex shrink-0 items-center gap-2.5 text-ink no-underline" aria-label="Job Scraper, all jobs">
          <Logo />
          {wide && <span className="text-base font-bold">Job Scraper</span>}
        </Link>
        <div className="flex h-11 min-w-0 flex-1 items-center gap-2 rounded-[10px] border border-line bg-bg px-3 lg:h-10">
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
        {wide ? (
          <div className="flex shrink-0 items-center gap-2">
            {NAV.map(([to, label]) => (
              <Link
                key={to}
                to={to}
                aria-current={pathname === to ? "page" : undefined}
                className="inline-flex h-10 items-center rounded-[10px] border border-line bg-surface px-3.5 font-medium text-ink no-underline hover:bg-chip aria-[current=page]:border-ok-bd aria-[current=page]:bg-ok-bg aria-[current=page]:text-ok-fg"
              >
                {label}
              </Link>
            ))}
            {onAddCompany && (
              <Button primary onClick={onAddCompany}>
                Add company
              </Button>
            )}
            <button
              type="button"
              onClick={() => setTheme(NEXT[theme])}
              aria-label={`Theme: ${THEME_LABEL[theme]}. Switch to ${THEME_LABEL[NEXT[theme]]}`}
              title={`Theme: ${THEME_LABEL[theme]}`}
              className={square}
            >
              <ThemeIcon mode={theme} />
            </button>
            <Menu
              label="Account"
              trigger={
                <span className="flex items-center gap-1.5">
                  Account
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" aria-hidden="true">
                    <path d="m6 9 6 6 6-6" />
                  </svg>
                </span>
              }
              buttonClassName="h-10 rounded-[10px] border border-line bg-surface px-3.5 font-medium text-ink hover:bg-chip"
            >
              {logouts}
            </Menu>
          </div>
        ) : (
          <Menu label="More actions" trigger={<MoreIcon />} buttonClassName={`${square} shrink-0`}>
            {onAddCompany && <MenuItem onSelect={onAddCompany}>Add company</MenuItem>}
            {pathname !== "/applications" && (
              <MenuItem onSelect={() => navigate("/applications")}>Your applications</MenuItem>
            )}
            {pathname !== "/sources" && <MenuItem onSelect={() => navigate("/sources")}>Sources</MenuItem>}
            <MenuItem keepOpen onSelect={() => setTheme(NEXT[theme])}>
              Theme: {THEME_LABEL[theme]}
            </MenuItem>
            <MenuSeparator />
            {logouts}
          </Menu>
        )}
      </div>
    </header>
  );
}

function MoreIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className="mx-auto">
      <circle cx="5" cy="12" r="1.8" />
      <circle cx="12" cy="12" r="1.8" />
      <circle cx="19" cy="12" r="1.8" />
    </svg>
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
