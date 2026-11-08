import { Link } from "@tanstack/react-router";
import {
  BookOpen,
  File,
  FileText,
  Globe,
  Image as ImageIcon,
  Mail,
  MessageSquare,
  PenLine,
  Presentation,
  Video,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import type { PageSource, PageSources } from "@/api/types";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { pageTo } from "./parts";

const GLYPH: Record<string, LucideIcon> = {
  pdf: FileText,
  web: Globe,
  youtube: Video,
  chat: MessageSquare,
  email: Mail,
  slides: Presentation,
  image: ImageIcon,
  handwritten: PenLine,
  page: BookOpen,
};

/** The page's sources; `undefined` while loading or when the endpoint is not there (public snapshots): nothing renders then. */
export function usePageSources(slug: string, kb: string | undefined, enabled: boolean): PageSource[] | undefined {
  const q = useApiQuery<PageSources>(
    ["pages", "sources", slug, kb ?? ""],
    (ds) => (kb ? ds.getPageSources(slug, { kb }) : ds.getPageSources(slug)),
    { enabled, retry: false, staleTime: 60_000 },
  );
  return q.data?.sources;
}

export const sourceNoun = (n: number) => `${n} source${n === 1 ? "" : "s"}`;

function SourceGlyph({ kind }: { kind: string }) {
  const Icon = GLYPH[kind] ?? File;
  return <Icon className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden />;
}

/** Where a click on a source goes: the raw item in the pipeline view, else the wiki page, else the web address. */
function SourceTitle({ s }: { s: PageSource }) {
  const cls = "min-w-0 truncate text-primary hover:underline";
  if (s.path_rel)
    return (
      <Link to={"/pipeline" as "/"} search={{ q: s.path_rel } as never} className={cls} title={`Open ${s.path_rel}`}>
        {s.title}
      </Link>
    );
  if (s.slug)
    return (
      <Link to={pageTo(s.slug)} className={cls}>
        {s.title}
      </Link>
    );
  if (s.url)
    return (
      <a href={s.url} target="_blank" rel="noopener noreferrer" className={cls}>
        {s.title}
      </a>
    );
  return <span className="min-w-0 truncate">{s.title}</span>;
}

export function SourceRow({ s }: { s: PageSource }) {
  return (
    <li className="flex min-w-0 items-start gap-2 text-sm" data-testid="page-source">
      <SourceGlyph kind={s.kind} />
      <div className="flex min-w-0 flex-1 flex-col">
        <span className="flex min-w-0 items-center gap-2">
          <SourceTitle s={s} />
          <span className="shrink-0 rounded border px-1 text-[11px] leading-4 text-muted-foreground">{s.disposition}</span>
        </span>
        <span className="truncate text-xs text-muted-foreground">
          {s.format}
          {s.added ? ` · ${s.added}` : ""}
          {s.cited_in_sections.length > 0 ? ` · cited in ${s.cited_in_sections.join(", ")}` : ""}
          {s.path_rel && s.slug ? (
            <>
              {" · "}
              <Link to={pageTo(s.slug)} className="hover:underline">
                page
              </Link>
            </>
          ) : null}
        </span>
      </div>
    </li>
  );
}

function SourceList({ sources }: { sources: PageSource[] }) {
  return (
    <ul className="flex flex-col gap-2" aria-label="Sources">
      {sources.map((s) => (
        <SourceRow key={s.id} s={s} />
      ))}
    </ul>
  );
}

/** Variant 1: a quiet section after the page text. */
export function SourcesFooter({ sources }: { sources: PageSource[] }) {
  if (!sources.length) return null;
  return (
    <section aria-label="Page sources" className="mt-2 flex flex-col gap-2 border-t pt-3">
      <h2 className="text-sm font-medium text-muted-foreground">
        Sources <span className="font-normal">{sources.length}</span>
      </h2>
      <SourceList sources={sources} />
    </section>
  );
}

/** Variant 2: a thin tab on the right edge of the window that slides a narrow panel over the page (no reflow). */
export function SourcesSideTab({ sources }: { sources: PageSource[] | undefined }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const n = sources?.length ?? 0;
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  if (!sources) return null;
  const tab = "rounded-l-md border border-r-0 bg-card px-1 py-3 text-xs text-muted-foreground [writing-mode:vertical-rl]";
  if (n === 0)
    return (
      <div className="fixed right-0 top-1/3 z-30" data-testid="sources-side-tab">
        <button type="button" disabled className={cn(tab, "cursor-default opacity-60")}>
          No sources
        </button>
      </div>
    );
  return (
    <div
      ref={ref}
      data-testid="sources-side-tab"
      className="fixed right-0 top-1/3 z-30 flex transition-transform duration-200 motion-reduce:transition-none"
      style={{ transform: open ? "translateX(0)" : "translateX(20rem)" }}
    >
      <button type="button" aria-expanded={open} aria-controls="sources-panel" onClick={() => setOpen(!open)} className={cn(tab, "hover:bg-accent")}>
        Sources · {n}
      </button>
      <div
        id="sources-panel"
        inert={!open}
        aria-hidden={!open}
        className="max-h-[60vh] w-80 overflow-y-auto border bg-card p-3 shadow-sm"
      >
        <SourceList sources={sources} />
      </div>
    </div>
  );
}

/** Variant 3a: the count in the page header; hover or click opens the list. */
export function SourcesCountMark({ sources }: { sources: PageSource[] }) {
  const [pinned, setPinned] = useState(false);
  const [hover, setHover] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const open = pinned || hover;
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setPinned(false);
        setHover(false);
      }
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPinned(false);
        setHover(false);
      }
    };
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [open]);
  if (!sources.length) return null;
  return (
    <span ref={ref} className="relative inline-flex" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} data-testid="sources-count-mark">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setPinned(!pinned)}
        className="rounded border px-1.5 py-0.5 text-xs text-muted-foreground hover:bg-accent"
      >
        {sourceNoun(sources.length)}
      </button>
      {open && (
        <div role="dialog" aria-label="Sources" className="absolute left-0 top-full z-30 w-80 max-w-[85vw] pt-1">
          <div className="max-h-72 overflow-y-auto rounded-lg border bg-card p-3 shadow-sm">
            <SourceList sources={sources} />
          </div>
        </div>
      )}
    </span>
  );
}

const norm = (s: string) => s.toLowerCase().replace(/\[([^\]]*)\]\([^)]*\)/g, "$1").replace(/[^\p{L}\p{N}]+/gu, "");

interface Dot {
  top: number;
  heading: string;
  titles: string[];
}

/** Variant 3b: a faint dot in the left margin beside each section heading that cites a source; hover names it. */
export function SourcesMarginDots({ sources, articleRef }: { sources: PageSource[]; articleRef: RefObject<HTMLElement | null> }) {
  const [dots, setDots] = useState<Dot[]>([]);
  const measure = useCallback(() => {
    const root = articleRef.current;
    if (!root) return;
    const by = new Map<string, PageSource[]>();
    for (const s of sources) for (const h of s.cited_in_sections) by.set(norm(h), [...(by.get(norm(h)) ?? []), s]);
    const base = root.getBoundingClientRect().top;
    const next: Dot[] = [];
    root.querySelectorAll("h2, h3, h4, h5").forEach((el) => {
      if (el.closest("header")) return;
      const hit = by.get(norm(el.textContent ?? ""));
      if (hit) next.push({ top: el.getBoundingClientRect().top - base + 8, heading: el.textContent ?? "", titles: hit.map((s) => s.title) });
    });
    setDots((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
  }, [sources, articleRef]);
  useLayoutEffect(() => {
    measure();
    const root = articleRef.current;
    if (!root || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(root);
    return () => ro.disconnect();
  }, [measure, articleRef]);
  return (
    <>
      {dots.map((d) => (
        <span key={d.heading} className="group absolute -left-4 z-10" style={{ top: d.top }} data-testid="sources-margin-dot">
          <button
            type="button"
            aria-label={`Cited here: ${d.titles.join(", ")}`}
            className="block size-2.5 rounded-full bg-muted-foreground/35 hover:bg-primary focus-visible:bg-primary"
          />
          <span className="pointer-events-none absolute left-0 top-full mt-1 hidden w-max max-w-64 rounded border bg-card px-2 py-1 text-xs text-muted-foreground shadow-sm group-hover:block group-focus-within:block">
            {d.titles.join(" · ")}
          </span>
        </span>
      ))}
    </>
  );
}
