import type { Heading, PhrasingContent, Root, RootContent } from "mdast";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { PageSource } from "@/api/types";
import { footerId, norm, SourceTitle } from "./PageSources";

/**
 * Numbered source markers: a small `[n]` in the page text where a source of the footer is cited, the popover that shows
 * the source on hover or focus, and the click that jumps to its footer entry. Presentation only: the markers are
 * added to the rendered tree (never to the page text), carry no text node (the number is drawn by CSS, so copying,
 * selecting and the flag/selection text matching never see it) and appear only with the Footer variant of "Sources on a page".
 */

export interface NumberedSource {
  n: number;
  s: PageSource;
}

/** The footer numbers its sources 1..n in the order the endpoint gives them. */
export const numberSources = (sources: PageSource[]): NumberedSource[] => sources.map((s, i) => ({ n: i + 1, s }));

const SLUG_SCHEME = "kbwiki:";
const PHRASING_PARENTS = new Set(["paragraph", "emphasis", "strong", "delete", "tableCell", "heading"]);
const SKIP = new Set(["code", "math", "inlineMath", "html", "yaml"]);
const MARK = "dataSourceMark";

type Parent = { type: string; children: RootContent[] };

const textOf = (n: unknown): string => {
  const x = n as { value?: string; children?: unknown[] };
  return typeof x.value === "string" ? x.value : (x.children ?? []).map(textOf).join("");
};

const markNode = (n: number): PhrasingContent =>
  ({ type: "emphasis", children: [], data: { hName: "sup", hProperties: { [MARK]: String(n) } } }) as unknown as PhrasingContent;

const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** What the text of the page can name a source by: its raw path, the file name and its web address. */
function needlesOf(s: PageSource): RegExp[] {
  const base = s.path_rel ? s.path_rel.split("/").pop() : "";
  return [s.path_rel, base, s.url]
    .filter((x): x is string => !!x)
    .map((x) => new RegExp(`(?<![\\w.-])${escape(x)}(?![\\w-])`));
}

/** The first place in `parent` that names `it` (a link to its page or address, or its path in text or code); the marker goes right after it. */
function place(parent: Parent, it: NumberedSource, needles: RegExp[]): boolean {
  const after = PHRASING_PARENTS.has(parent.type);
  for (let i = 0; i < parent.children.length; i++) {
    const c = parent.children[i]!;
    if (SKIP.has(c.type)) continue;
    if (c.type === "link") {
      const hit = c.url.startsWith(SLUG_SCHEME) ? !!it.s.slug && safeDecode(c.url.slice(SLUG_SCHEME.length)) === it.s.slug : !!it.s.url && c.url === it.s.url;
      if (hit && after) {
        parent.children.splice(i + 1, 0, markNode(it.n) as RootContent);
        return true;
      }
    } else if (c.type === "text" && after) {
      for (const re of needles) {
        const m = re.exec(c.value);
        if (!m) continue;
        const end = m.index + m[0].length;
        const rest = c.value.slice(end);
        c.value = c.value.slice(0, end);
        parent.children.splice(i + 1, 0, markNode(it.n) as RootContent, ...(rest ? [{ type: "text", value: rest } as RootContent] : []));
        return true;
      }
    } else if (c.type === "inlineCode" && after) {
      if (needles.some((re) => re.test(c.value))) {
        parent.children.splice(i + 1, 0, markNode(it.n) as RootContent);
        return true;
      }
    } else if ("children" in c && place(c as unknown as Parent, it, needles)) return true;
  }
  return false;
}

const safeDecode = (s: string) => {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
};

/**
 * Remark plugin (run after the wikilinks one). For each source and each section the endpoint says cites it
 * (`cited_in_sections`): the marker goes after the first link or mention that names it in that section; when the text names
 * it in no way the tree can find, it goes at the end of the section's heading. `## My notes` and everything after it
 * (it is always the last section), code and headings' own text never get one. A source that no section cites gets none.
 */
export function remarkSourceMarks(items: NumberedSource[]) {
  const withNeedles = items.map((it) => ({ it, needles: needlesOf(it.s), sections: new Set(it.s.cited_in_sections.map(norm)) }));
  return () => (tree: Root) => {
    let heading: Heading | null = null;
    let section = "";
    let placed = new Set<number>();
    const flush = () => {
      if (!heading) return;
      for (const { it, sections } of withNeedles) if (sections.has(section) && !placed.has(it.n)) heading.children.push(markNode(it.n));
    };
    for (const block of tree.children) {
      if (block.type === "heading") {
        flush();
        heading = block;
        section = norm(textOf(block));
        placed = new Set();
        if (section === "mynotes") {
          heading = null;
          break;
        }
        continue;
      }
      if (!heading) continue;
      for (const { it, needles, sections } of withNeedles) {
        if (sections.has(section) && !placed.has(it.n) && "children" in block && place(block as unknown as Parent, it, needles)) placed.add(it.n);
      }
    }
    flush();
  };
}

/** Click on a marker: bring its footer entry into view and highlight it for a moment. */
export function showFooterEntry(n: number) {
  const el = document.getElementById(footerId(n));
  if (!el) return;
  const calm = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  el.scrollIntoView?.({ block: "center", behavior: calm ? "auto" : "smooth" });
  el.setAttribute("data-flash", "");
  window.setTimeout(() => el.removeAttribute("data-flash"), 1800);
}

const GAP = 8;
const EDGE = 8;

/**
 * The popover's place: below the cited block (the sentence's own paragraph, item or heading) with a gap, above it when
 * there is no room below, and kept inside the window; so it never covers the text it belongs to. `at` is the block's
 * vertical extent and the marker's horizontal one.
 */
export function placePopover(at: { left: number; top: number; bottom: number; width: number }, size: { w: number; h: number }, view: { w: number; h: number }) {
  const below = at.bottom + GAP + size.h + EDGE <= view.h;
  const top = below ? at.bottom + GAP : Math.max(EDGE, at.top - GAP - size.h);
  const left = Math.min(Math.max(at.left + at.width / 2 - size.w / 2, EDGE), Math.max(EDGE, view.w - size.w - EDGE));
  return { left, top, below };
}

/** One marker: `[n]` in the text; hover or keyboard focus shows the source, click goes to the footer entry. */
export function SourceMarker({ item }: { item: NumberedSource }) {
  const { n, s } = item;
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const [at, setAt] = useState<{ left: number; top: number } | null>(null);
  const id = useId();
  const show = () => {
    clearTimeout(timer.current);
    setOpen(true);
  };
  const hide = () => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(false), 150);
  };
  useEffect(() => () => clearTimeout(timer.current), []);
  const measure = useCallback(() => {
    const b = btn.current?.getBoundingClientRect();
    const p = pop.current;
    if (!b || !p) return;
    const blk = btn.current?.closest("p, li, h1, h2, h3, h4, h5, h6, blockquote, td")?.getBoundingClientRect();
    const next = placePopover({ left: b.left, width: b.width, top: blk ? Math.min(blk.top, b.top) : b.top, bottom: blk ? Math.max(blk.bottom, b.bottom) : b.bottom },  { w: p.offsetWidth, h: p.offsetHeight }, { w: window.innerWidth, h: window.innerHeight });
    setAt((prev) => (prev && prev.left === next.left && prev.top === next.top ? prev : { left: next.left, top: next.top }));
  }, []);
  useLayoutEffect(() => {
    if (!open) return setAt(null);
    measure();
    window.addEventListener("scroll", measure, true);
    window.addEventListener("resize", measure);
    return () => {
      window.removeEventListener("scroll", measure, true);
      window.removeEventListener("resize", measure);
    };
  }, [open, measure]);
  return (
    <>
      <sup className="kb-src-sup">
        <button
          ref={btn}
          type="button"
          className="kb-src"
          data-n={n}
          data-testid="source-marker"
          aria-label={`Source ${n}: ${s.title}`}
          aria-describedby={open ? id : undefined}
          onMouseEnter={show}
          onMouseLeave={hide}
          onFocus={show}
          onBlur={hide}
          onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
          onClick={() => showFooterEntry(n)}
        />
      </sup>
      {open &&
        createPortal(
          <div
            ref={pop}
            id={id}
            role="dialog"
            aria-label={`Source ${n}`}
            onMouseEnter={show}
            onMouseLeave={hide}
            className="fixed z-50 w-72 max-w-[calc(100vw-16px)] rounded-md border bg-card p-3 text-sm shadow-sm"
            style={{ left: at?.left ?? 0, top: at?.top ?? 0, visibility: at ? "visible" : "hidden" }}
          >
            <div className="flex min-w-0 items-baseline gap-2">
              <span className="text-xs tabular-nums text-muted-foreground">{n}</span>
              <SourceTitle s={s} />
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {s.kind} · {s.disposition}
              {s.added ? ` · ${s.added}` : ""}
            </p>
            <p className="break-all text-xs text-muted-foreground">
              Filed in {s.format}
              {s.path_rel ? `: ${s.path_rel}` : ""}
            </p>
          </div>,
          document.body,
        )}
    </>
  );
}
