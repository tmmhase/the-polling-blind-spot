import type { ReactNode } from "react";

export function Section({
  id,
  eyebrow,
  title,
  lede,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  lede?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-20 border-t border-line py-12">
      <div className="mb-6 max-w-3xl">
        <p className="text-[0.72rem] font-semibold uppercase tracking-[0.16em] text-copper">{eyebrow}</p>
        <h2 className="mt-2 font-serif text-3xl leading-tight text-ink sm:text-4xl">{title}</h2>
        {lede ? <p className="mt-3 text-[0.98rem] leading-relaxed text-muted">{lede}</p> : null}
      </div>
      {children}
    </section>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-lg border border-line bg-card p-4 shadow-card ${className}`}>{children}</div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="border-l-2 border-copper bg-card px-4 py-3 text-sm leading-relaxed text-muted">{children}</p>
  );
}

const NAV = [
  ["map", "Map"],
  ["errors", "Errors"],
  ["pollsters", "Pollsters"],
  ["trends", "Trends"],
  ["uncertainty", "Uncertainty"],
  ["notes", "Notes"],
] as const;

export function TopBar() {
  return (
    <header className="sticky top-0 z-20 border-b border-line/80 bg-paper/90 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
        <a href="#top" className="font-serif text-lg leading-none text-ink">
          The Polling Blind Spot
        </a>
        <nav aria-label="Sections" className="flex gap-1 overflow-x-auto text-sm">
          {NAV.map(([id, label]) => (
            <a
              key={id}
              href={`#${id}`}
              className="shrink-0 rounded px-2 py-1 text-muted hover:bg-card hover:text-ink"
            >
              {label}
            </a>
          ))}
        </nav>
      </div>
    </header>
  );
}
