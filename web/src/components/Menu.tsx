import { createContext, type ReactNode, useContext, useEffect, useId, useRef, useState } from "react";

const CloseMenu = createContext<() => void>(() => undefined);

type MenuProps = {
  /** The button's accessible name, e.g. "More actions". */
  label: string;
  /** What the button shows; defaults to the label. */
  trigger?: ReactNode;
  buttonClassName: string;
  children: ReactNode;
};

/**
 * A button that opens a list of actions (WAI-ARIA menu button).
 * Esc or a click outside closes it; ↑/↓, Home and End move between items.
 */
export function Menu({ label, trigger, buttonClassName, children }: MenuProps) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  const id = useId();

  function close(refocus = true) {
    setOpen(false);
    if (refocus) button.current?.focus();
  }

  useEffect(() => {
    if (!open) return;
    box.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const outside = (e: PointerEvent) => {
      if (!box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open) return;
    if (e.key === "Escape" || e.key === "Tab") {
      if (e.key === "Escape") e.preventDefault();
      close(e.key === "Escape");
      return;
    }
    const items = [...(box.current?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];
    const at = items.indexOf(document.activeElement as HTMLElement);
    const go: Record<string, number> = {
      ArrowDown: (at + 1) % items.length,
      ArrowUp: (at - 1 + items.length) % items.length,
      Home: 0,
      End: items.length - 1,
    };
    if (e.key in go) {
      e.preventDefault();
      items[go[e.key]]?.focus();
    }
  }

  return (
    <div ref={box} className="relative" onKeyDown={onKeyDown}>
      <button
        ref={button}
        type="button"
        aria-label={trigger ? label : undefined}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        className={`${buttonClassName} ${open ? "bg-chip" : ""}`}
        onClick={() => setOpen(!open)}
      >
        {trigger ?? label}
      </button>
      {open && (
        <div
          id={id}
          role="menu"
          aria-label={label}
          className="absolute right-0 z-20 mt-2 w-60 rounded-xl border border-line bg-surface p-1.5 shadow-[0_12px_32px_rgb(0_0_0/0.25)]"
        >
          <CloseMenu.Provider value={close}>{children}</CloseMenu.Provider>
        </div>
      )}
    </div>
  );
}

type ItemProps = {
  onSelect: () => void;
  /** Leave the menu open after selecting, e.g. to cycle the theme. */
  keepOpen?: boolean;
  danger?: boolean;
  children: ReactNode;
};

export function MenuItem({ onSelect, keepOpen, danger, children }: ItemProps) {
  const close = useContext(CloseMenu);
  return (
    <button
      type="button"
      role="menuitem"
      tabIndex={-1}
      className={`flex h-11 w-full items-center rounded-lg px-3 text-left hover:bg-chip focus:bg-chip focus:outline-none lg:h-10 ${
        danger ? "text-warn-fg" : "text-ink"
      }`}
      onClick={() => {
        if (!keepOpen) close();
        onSelect();
      }}
    >
      {children}
    </button>
  );
}

export function MenuSeparator() {
  return <hr role="separator" className="mx-1 my-1.5 border-0 border-t border-line" />;
}
