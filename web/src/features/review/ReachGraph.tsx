import { Search, X } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { fixedChannel, GraphLegend, NodeMarkG, registerTypeMarks, typeMarksRegistered } from "@/features/graph/encoding";
import { REACH_COLORS } from "@/theme/palette";
import type { GNode } from "@/features/graph/types";
import { cn } from "@/lib/utils";
import type { Reach, ReachPage, ReachRel } from "./api";
import { plural } from "./model";

export interface Picked {
  slug: string;
  title: string;
}

export interface Found {
  pages: Picked[];
  explanation: string;
  cypher: string | null;
}

export interface ReachGraphHandle {
  focusSearch: () => void;
  /** move the keyboard focus to the next (1) or previous (-1) node */
  move: (dir: 1 | -1) => void;
  /** select or deselect the focused node */
  toggleFocused: () => void;
}

const DRAWN = 24;
const FOUND_DRAWN = 12;
const R_INNER = 70;
const R_OUTER = 115;
const R_FOUND = 138;
const NODE = 5;

const REL_LINE: Record<ReachRel, string> = {
  added: "This change adds the link",
  removed: "This change removes the link",
  in: "Links to this page",
  out: "This page links to it",
};
const REL_DOT: Record<ReachRel | "found", string> = {
  added: "bg-green-600",
  removed: "border border-red-500",
  in: "bg-slate-500",
  out: "bg-slate-400",
  found: "bg-amber-500",
};

export const EXAMPLES = ["pages that cite the same source", "pages nobody links to", "everything two links away"];
export const isCypher = (text: string) => /^\s*MATCH\b/i.test(text);

/**
 * The wiki pages in a graph query's rows: any cell (or list cell) that is a page slug, a `<kb>:<slug>` id, or a node
 * with one of those as `slug`/`id`. Unknown values are skipped; order is first appearance.
 */
export function pagesFromRows(rows: unknown[][], titles: ReadonlyMap<string, string>, exclude: string): Picked[] {
  const seen = new Set<string>([exclude]);
  const out: Picked[] = [];
  const visit = (v: unknown) => {
    if (Array.isArray(v)) return v.forEach(visit);
    const raw = typeof v === "string" ? v : v && typeof v === "object" ? (v as Record<string, unknown>).slug ?? (v as Record<string, unknown>).id : null;
    if (typeof raw !== "string") return;
    const slug = titles.has(raw) ? raw : raw.slice(raw.indexOf(":") + 1);
    if (!titles.has(slug) || seen.has(slug)) return;
    seen.add(slug);
    out.push({ slug, title: titles.get(slug)! });
  };
  rows.forEach(visit);
  return out;
}

type Node = { slug: string; title: string; type?: string; rel: ReachRel | "found"; exists: boolean; x: number; y: number };

/** Colour is the relation to the change (the mark stays the page's type); removed and missing pages are hollow. */
const REL_COLOR: Record<ReachRel | "found", string> = REACH_COLORS;
const REL_LABEL: Record<ReachRel | "found", string> = { added: "link added", removed: "link removed", in: "links here", out: "linked from here", found: "found" };
const relOf = (n: GNode) => (n as unknown as { rel: ReachRel | "found" }).rel;
const RELATION = fixedChannel("reach", "link", relOf, (Object.keys(REL_COLOR) as (ReachRel | "found")[]).map((key) => ({ key, label: REL_LABEL[key], color: REL_COLOR[key] })));
/**
 * Give the pages' own types their marks when no graph has (the Graph screen does it from the full schema, and wins:
 * once it has, this never touches them). Seeds the union of the types seen here, so marks stay stable across cards.
 */
let seeded: Set<string> | null = null;
function seedTypeMarks(types: string[]) {
  if (typeMarksRegistered() && !seeded) return;
  const all = new Set([...(seeded ?? []), ...types]);
  if (seeded && all.size === seeded.size) return;
  seeded = all;
  registerTypeMarks([...all].sort().map((id) => ({ id, layer: "concept" })));
}

/** A drawn page as a graph node, for the shared legend (mark by type, colour by its link to the change). */
const asGNode = (n: Node): GNode => ({ id: n.slug, label: n.title, title: n.title, type: n.type ?? "concept", layer: "concept", areas: [], year: null, inDegree: 0, outDegree: 0, path: "", added: "", rel: n.rel }) as unknown as GNode;

/** Angles spread over [a0, a1] (degrees, 0 = right, clockwise), half a step in from each end. */
function spread(n: number, a0: number, a1: number): number[] {
  if (!n) return [];
  const step = (a1 - a0) / n;
  return Array.from({ length: n }, (_, i) => a0 + step * (i + 0.5));
}
const at = (r: number, deg: number) => ({ x: r * Math.cos((deg * Math.PI) / 180), y: r * Math.sin((deg * Math.PI) / 180) });

/**
 * Radial, not force: the card's page in the middle; the inner ring is what this change alters (links added,
 * removed), the outer ring the pages around it (linking here on the left, linked from here on the right), found
 * pages an amber arc outside. Deterministic, so nothing moves between cards.
 */
export function layout(reach: Reach | undefined, found: Picked[]): { nodes: Node[]; more: number } {
  const pages = (reach?.pages ?? []).slice(0, DRAWN);
  const inner = pages.filter((p) => p.rel === "added" || p.rel === "removed");
  const ins = pages.filter((p) => p.rel === "in");
  const outs = pages.filter((p) => p.rel === "out");
  const node = (p: ReachPage, r: number, deg: number): Node => ({ ...p, ...at(r, deg) });
  const nodes: Node[] = [
    ...spread(inner.length, -90, 270).map((d, i) => node(inner[i]!, R_INNER, d)),
    ...spread(ins.length, 100, 260).map((d, i) => node(ins[i]!, R_OUTER, d)),
    ...spread(outs.length, -80, 80).map((d, i) => node(outs[i]!, R_OUTER, d)),
  ];
  const known = new Set(pages.map((p) => p.slug));
  const extra = found.filter((p) => !known.has(p.slug)).slice(0, FOUND_DRAWN);
  nodes.push(...spread(extra.length, 200, 340).map((d, i): Node => ({ ...extra[i]!, rel: "found", exists: true, ...at(R_FOUND, d) })));
  return { nodes, more: Math.max(0, (reach?.total ?? 0) - pages.length) };
}

function counts(reach: Reach | undefined) {
  const c = { added: 0, removed: 0, in: 0, out: 0 };
  for (const p of reach?.pages ?? []) c[p.rel]++;
  return c;
}

/**
 * The left panel: what the card on screen touches, a search line that brings more pages in (plain words through the
 * model, or Cypher starting with MATCH), and the selection that goes with the next edit.
 */
export const ReachGraph = forwardRef<ReachGraphHandle, {
  cardId: string;
  center: { title: string; isNew: boolean };
  reach: Reach | undefined;
  selected: Picked[];
  onToggle: (p: Picked) => void;
  search: (text: string) => Promise<Found>;
}>(function ReachGraph({ cardId, center, reach, selected, onToggle, search }, ref) {
  const [text, setText] = useState("");
  const [found, setFound] = useState<Found | null>(null);
  const [state, setState] = useState<"idle" | "looking" | "error" | "empty">("idle");
  const [error, setError] = useState("");
  const [showQuery, setShowQuery] = useState(false);
  const [focused, setFocused] = useState(false);
  const [hover, setHover] = useState<string | null>(null);
  const [cursor, setCursor] = useState(-1);
  const [listOpen, setListOpen] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const cache = useRef(new Map<string, Found>());
  const run = useRef(0);

  useEffect(() => {
    setText("");
    setFound(null);
    setState("idle");
    setCursor(-1);
    setShowQuery(false);
    run.current++;
  }, [cardId]);

  const { nodes, more } = useMemo(() => layout(reach, found?.pages ?? []), [reach, found]);
  const legendNodes = useMemo(() => {
    seedTypeMarks([...new Set(nodes.map((n) => n.type ?? "concept"))]);
    return nodes.map(asGNode);
  }, [nodes]);
  const picked = useMemo(() => new Set(selected.map((p) => p.slug)), [selected]);
  const labelsAlways = nodes.length <= 8;
  const c = counts(reach);

  useImperativeHandle(ref, () => ({
    focusSearch: () => input.current?.focus(),
    move: (dir) => setCursor((i) => (nodes.length ? (i + dir + nodes.length) % nodes.length : -1)),
    toggleFocused: () => {
      const n = nodes[cursor];
      if (n) onToggle({ slug: n.slug, title: n.title });
    },
  }), [nodes, cursor, onToggle]);

  const go = async (q: string) => {
    const t = q.trim();
    if (!t) return;
    const key = `${cardId}\u0000${t}`;
    const hit = cache.current.get(key);
    if (hit) {
      setFound(hit);
      setState(hit.pages.length ? "idle" : "empty");
      return;
    }
    const mine = ++run.current;
    setState("looking");
    setShowQuery(false);
    try {
      const res = await search(t);
      if (mine !== run.current) return;
      cache.current.set(key, res);
      setFound(res);
      setState(res.pages.length ? "idle" : "empty");
    } catch (e) {
      if (mine !== run.current) return;
      setFound(null);
      setError(e instanceof Error ? e.message : String(e));
      setState("error");
    }
  };
  const clear = () => {
    run.current++;
    setText("");
    setFound(null);
    setState("idle");
  };

  const cypher = isCypher(text);
  const extraFound = (found?.pages ?? []).filter((p) => !(reach?.pages ?? []).some((r) => r.slug === p.slug));
  return (
    <section className="flex flex-col gap-2" aria-label="What this change touches" data-tour="review-reach">
      <div className="relative">
        <div className={cn("flex h-8 items-center gap-1.5 rounded-md border bg-background px-2 focus-within:ring-2 focus-within:ring-ring", cypher && "font-mono")}>
          <Search className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
          <input
            ref={input}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setTimeout(() => setFocused(false), 120)}
            onKeyDown={(e) => {
              e.stopPropagation();
              if (e.key === "Enter") {
                e.preventDefault();
                void go(text);
              } else if (e.key === "Escape") {
                if (text || found) clear();
                else input.current?.blur();
              }
            }}
            aria-label="Find pages to add to the graph"
            placeholder="Find pages to add…"
            className="min-w-0 flex-1 bg-transparent text-xs outline-none placeholder:text-muted-foreground"
          />
          {cypher && <span className="rounded bg-muted px-1 font-sans text-[10px] text-muted-foreground">Cypher</span>}
          {(text || found) && (
            <button type="button" aria-label="Clear the search" className="text-muted-foreground hover:text-foreground" onClick={clear}>
              <X className="size-3.5" aria-hidden />
            </button>
          )}
        </div>
        {focused && !text && (
          <div className="absolute left-0 right-0 top-full z-20 mt-1 flex flex-col gap-0.5 rounded-md border bg-popover p-1.5 text-xs shadow-[var(--shadow)]">
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" className="rounded px-1.5 py-1 text-left hover:bg-accent" onMouseDown={(e) => e.preventDefault()} onClick={() => { setText(ex); void go(ex); }}>
                {ex}
              </button>
            ))}
            <p className="px-1.5 pt-1 text-[11px] text-muted-foreground">Plain words use the model. Queries starting with MATCH don't.</p>
          </div>
        )}
      </div>
      {state === "looking" && <p className="text-[11px] text-muted-foreground" aria-live="polite">Looking…</p>}
      {state === "empty" && <p className="text-[11px] text-muted-foreground">Nothing matched. Try other words.</p>}
      {state === "error" && <p role="alert" className="text-[11px] text-bad" title={error}>Couldn't run that search. <span className="text-muted-foreground">{error}</span></p>}
      {found && state === "idle" && (
        <p className="text-[11px] text-muted-foreground">
          {found.explanation || `Found ${plural(found.pages.length, "page")}.`}{" "}
          {found.cypher && (
            <button type="button" className="underline underline-offset-2 hover:text-foreground" onClick={() => setShowQuery((x) => !x)}>{showQuery ? "Hide query" : "Show query"}</button>
          )}
        </p>
      )}
      {showQuery && found?.cypher && <pre className="max-h-24 overflow-auto whitespace-pre-wrap rounded bg-muted p-1.5 font-mono text-[10px]">{found.cypher}</pre>}

      <div>
        <p className="text-sm font-medium">{reach?.total ? `Touches ${plural(reach.total, "page")}` : "Touches no other pages."}</p>
        {!!reach?.total && (
          <p className="flex flex-wrap gap-x-2 text-[11px] text-muted-foreground">
            {([["added", `${c.added} added`], ["removed", `${c.removed} removed`], ["in", `${c.in} lean on it`], ["out", `${c.out} linked from it`]] as const)
              .filter(([k]) => c[k] > 0)
              .map(([k, label]) => (
                <span key={k}>{label}</span>
              ))}
          </p>
        )}
      </div>

      <svg viewBox="-150 -150 300 300" className="h-[280px] w-full overflow-visible" role="group" aria-label={`The page and the ${plural(nodes.length, "page")} around it`}>
        {nodes.map((n) => (
          <line
            key={`e-${n.slug}`}
            x1={0} y1={0} x2={n.x} y2={n.y}
            className={cn(n.rel === "added" ? "stroke-green-600" : n.rel === "removed" ? "stroke-red-500" : n.rel === "found" ? "stroke-amber-400/50" : "stroke-slate-300")}
            strokeWidth={n.rel === "added" || n.rel === "removed" ? 1.5 : 0.75}
            strokeDasharray={n.rel === "removed" ? "4 3" : n.rel === "found" ? "1 3" : undefined}
          />
        ))}
        <g className="text-foreground" strokeDasharray={center.isNew ? "4 3" : undefined}>
          <NodeMarkG type="concept" x={0} y={0} r={14} color="currentColor" background="var(--card, #fff)" />
        </g>
        <text y={28} textAnchor="middle" className="fill-foreground text-[10px] font-medium">{center.title.length > 24 ? `${center.title.slice(0, 23)}…` : center.title}</text>
        {center.isNew && <text y={4} textAnchor="middle" className="fill-muted-foreground text-[8px] font-semibold">New</text>}
        {nodes.map((n, i) => {
          const sel = picked.has(n.slug);
          const label = labelsAlways || sel || hover === n.slug || cursor === i;
          const tip = n.rel === "found" ? "Found by your search" : n.exists ? REL_LINE[n.rel] : "Page doesn't exist yet";
          const color = RELATION.color(asGNode(n));
          const hollow = !n.exists || n.rel === "removed";
          const right = n.x >= 0;
          return (
            <g
              key={n.slug}
              transform={`translate(${n.x} ${n.y})`}
              role="button"
              aria-pressed={sel}
              aria-label={`${n.title}: ${tip}`}
              className="cursor-pointer"
              onClick={() => onToggle({ slug: n.slug, title: n.title })}
              onMouseEnter={() => setHover(n.slug)}
              onMouseLeave={() => setHover(null)}
            >
              <title>{`${n.title} — ${tip}`}</title>
              <rect x={-10} y={-10} width={20} height={20} fill="transparent" />
              {sel && <circle r={NODE + 3} className="fill-none stroke-blue-600" strokeWidth={2} />}
              {cursor === i && !sel && <circle r={NODE + 3} className="fill-none stroke-foreground/50" strokeWidth={1} strokeDasharray="2 2" />}
              <g strokeDasharray={!n.exists ? "2 1.5" : undefined}>
                <NodeMarkG type={n.type ?? "concept"} x={0} y={0} r={NODE} color={color} background={hollow ? "none" : color} />
              </g>
              {label && (
                <text x={right ? 9 : -9} y={3} textAnchor={right ? "start" : "end"} className={cn("text-[9px]", sel ? "fill-blue-700 font-medium" : "fill-foreground")}>
                  {n.title.length > 22 ? `${n.title.slice(0, 21)}…` : n.title}
                </text>
              )}
            </g>
          );
        })}
        {more > 0 && (
          <g className="cursor-pointer" onClick={() => setListOpen(true)} role="button" aria-label={`${more} more pages: show the list`}>
            <rect x={-26} y={128} width={52} height={16} rx={8} className="fill-muted" />
            <text y={139} textAnchor="middle" className="fill-muted-foreground text-[9px]">+{more} more</text>
          </g>
        )}
      </svg>
      {nodes.length > 0 && <GraphLegend nodes={legendNodes} color={RELATION} density="compact" />}

      {(!!reach?.pages.length || extraFound.length > 0) && (
        <details open={listOpen} onToggle={(e) => setListOpen((e.target as HTMLDetailsElement).open)} className="text-xs">
          <summary className="cursor-pointer text-[11px] text-muted-foreground">List</summary>
          <ul className="mt-1 flex max-h-64 flex-col gap-0.5 overflow-auto">
            {(reach?.pages ?? []).map((p) => (
              <ListRow key={p.slug} page={p} dot={REL_DOT[p.rel]} line={p.exists ? REL_LINE[p.rel] : "Page doesn't exist yet"} checked={picked.has(p.slug)} onToggle={onToggle} />
            ))}
            {reach && reach.total > reach.pages.length && <li className="px-1 text-[11px] text-muted-foreground">and {reach.total - reach.pages.length} more not shown</li>}
            {extraFound.length > 0 && <li className="px-1 pt-1 text-[11px] font-medium text-muted-foreground">Found · {extraFound.length}</li>}
            {extraFound.map((p) => (
              <ListRow key={`f-${p.slug}`} page={p} dot={REL_DOT.found} line="Found by your search" checked={picked.has(p.slug)} onToggle={onToggle} />
            ))}
          </ul>
        </details>
      )}
    </section>
  );
});

function ListRow({ page, dot, line, checked, onToggle }: { page: Picked; dot: string; line: string; checked: boolean; onToggle: (p: Picked) => void }) {
  return (
    <li>
      <label className="flex cursor-pointer items-center gap-1.5 rounded px-1 py-0.5 hover:bg-accent" title={line}>
        <input type="checkbox" checked={checked} onChange={() => onToggle({ slug: page.slug, title: page.title })} className="size-3" />
        <span className={cn("inline-block size-2 shrink-0 rounded-full", dot)} aria-hidden />
        <span className="truncate">{page.title}</span>
      </label>
    </li>
  );
}
