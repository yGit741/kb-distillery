import { useEffect, useMemo, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { NodeSwatch, SourceIcon } from "../encoding/NodeMarkSvg";
import { GLYPH_LABEL, type SourceGlyph } from "../encoding/spec";
import type { NeighborMap } from "../graphData";
import { pluralize } from "../shell/corners/typeGroups";
import { SEARCH_LINE_H, useShellTop } from "../shell/layout";
import { useGraphUi } from "../store";
import { colorOf, supportOf, SUPPORT_LABEL } from "../style";
import type { GNode } from "../types";
import { kindDetail, kindLine } from "./model";

const RING = "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const ROW = 28;
const GAP_W = 220;
/** a long kind draws its busiest sources; the rest is said in words, never cut silently */
const MAX_SOURCES = 250;
/** an idle list shows this many pages until it is opened */
const IDLE_ROWS = 5;

const titleOf = (n: GNode): string => n.title || n.id;

interface Props {
  kind: SourceGlyph;
  nodes: readonly GNode[];
  neighbors: NeighborMap;
  byId: ReadonlyMap<string, GNode>;
  /** source pages behind each concept, over the whole knowledge base */
  support: ReadonlyMap<string, number>;
  onRead: (id: string) => void;
  onClose: () => void;
}

/**
 * Inside a source kind (flag knowledge-health). First what needs care: the sources that feed nothing yet, waiting to
 * be digested or digested with no concept (a few of each, the rest on demand). Then the kind's sources in use on the
 * left and the concepts they feed on the right, least supported first, a line for every link between the two.
 * Resting on a row lights its links; pressing it opens the page.
 */
export function KindView({ kind, nodes, neighbors, byId, support, onRead, onClose }: Props) {
  const d = useMemo(() => kindDetail(kind, nodes, neighbors, byId, support), [kind, nodes, neighbors, byId, support]);
  const [hot, setHot] = useState<string | null>(null);
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  // the search line floats over the top of the area: the kind starts under it
  const top = useShellTop() + SEARCH_LINE_H + 14;
  // Esc leaves the kind, unless a page is open over it: then Esc closes the page first (capture: read before it closes)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || useGraphUi.getState().readerSlug) return;
      const t = e.target;
      if (t instanceof HTMLElement && t.matches("input, textarea, select, [contenteditable=true]")) return;
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  const sources = d.sources.slice(0, MAX_SOURCES);
  const more = d.sources.length - sources.length;
  const concepts = useMemo(() => {
    if (!more) return d.concepts;
    const drawn = new Set(sources.flatMap((s) => s.concepts));
    return d.concepts.filter((c) => drawn.has(c.node.id));
  }, [d, sources, more]);
  const rowOf = useMemo(() => new Map(concepts.map((c, i) => [c.node.id, i] as const)), [concepts]);
  const links = useMemo(() => sources.flatMap((s, i) => s.concepts.filter((c) => rowOf.has(c)).map((c) => ({ s: s.node.id, c, from: i, to: rowOf.get(c)! }))), [sources, rowOf]);
  const lit = useMemo(() => {
    if (!hot) return null;
    const out = new Set<string>([hot]);
    for (const l of links) {
      if (l.s === hot) out.add(l.c);
      if (l.c === hot) out.add(l.s);
    }
    return out;
  }, [hot, links]);
  const total = d.sources.length + d.waiting.length + d.unlinked.length;
  const label = pluralize(GLYPH_LABEL[kind]);
  const height = Math.max(sources.length, concepts.length) * ROW;
  const y = (i: number) => i * ROW + ROW / 2;
  const dim = (id: string) => (lit && !lit.has(id) ? "opacity-35" : "");
  const hover = (id: string) => ({ onPointerEnter: () => setHot(id), onPointerLeave: () => setHot((h) => (h === id ? null : h)), onFocus: () => setHot(id), onBlur: () => setHot((h) => (h === id ? null : h)) });

  const idle = (title: string, why: string, pages: readonly GNode[]) =>
    pages.length > 0 && (
      <section className="min-w-0" data-idle={title}>
        <h3 className="text-[12px] text-foreground">
          {title} <span className="tabular-nums text-muted-foreground">{pages.length}</span>
        </h3>
        <p className="text-[11px] text-muted-foreground">{why}</p>
        <ul className="mt-1.5">
          {(open.has(title) ? pages : pages.slice(0, IDLE_ROWS)).map((n) => (
            <li key={n.id}>
              <button type="button" onClick={() => onRead(n.id)} title={titleOf(n)} className={cn("flex h-7 w-full min-w-0 items-center gap-2 rounded-md px-2 text-left text-[12px] text-muted-foreground hover:bg-accent hover:text-foreground", RING)}>
                <SourceIcon type={n.type} className="size-3.5 flex-none" />
                <span className="truncate">{titleOf(n)}</span>
              </button>
            </li>
          ))}
        </ul>
        {pages.length > IDLE_ROWS && (
          <button
            type="button"
            aria-expanded={open.has(title)}
            onClick={() => setOpen((o) => new Set(o.has(title) ? [...o].filter((t) => t !== title) : [...o, title]))}
            className={cn("mt-0.5 h-7 rounded-md px-2 text-[12px] text-muted-foreground hover:bg-accent hover:text-foreground", RING)}
          >
            {open.has(title) ? "Show fewer" : `Show all ${pages.length}`}
          </button>
        )}
      </section>
    );

  return (
    <div data-health="kind" role="region" aria-label={`${label}: sources and the concepts they feed`} className="pointer-events-auto absolute inset-0 z-[26] flex flex-col bg-background" style={{ paddingTop: top }}>
      <header className="mx-auto flex w-full max-w-[1072px] flex-none flex-wrap items-center gap-x-3 gap-y-1 px-4 pb-4">
        <button type="button" onClick={onClose} className={cn("flex h-7 items-center gap-1.5 rounded-full pl-2 pr-3 text-[12px] text-muted-foreground hover:bg-accent hover:text-foreground", RING)}>
          <ArrowLeft className="size-3.5" aria-hidden />
          Health
        </button>
        <h2 className="flex items-center gap-2 text-[14px] font-medium text-foreground">
          <SourceIcon type={d.sources[0]?.node.type ?? d.waiting[0]?.type ?? d.unlinked[0]?.type ?? kind} className="size-4" />
          {label}
        </h2>
        <p className="text-[12px] text-muted-foreground">
          <span className="tabular-nums">{total}</span> sources, {kindLine({ waiting: d.waiting.length, unlinked: d.unlinked.length })}
        </p>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-10">
        <div className="mx-auto w-full max-w-[1040px]">
          {(d.waiting.length > 0 || d.unlinked.length > 0) && (
            <div className="mb-6 grid grid-cols-1 items-start gap-x-10 gap-y-5 border-b pb-5 md:grid-cols-2">
              {idle("Waiting", "Listed, not digested yet.", d.waiting)}
              {idle("Feed no concept", "Digested, but linked to no concept page.", d.unlinked)}
            </div>
          )}
          {sources.length > 0 ? (
            <>
              <div className="flex text-[11px] text-muted-foreground">
                <div className="min-w-0 flex-1 px-2 pb-1">In use: digested and linked to a concept</div>
                <div className="flex-none" style={{ width: GAP_W }} />
                <div className="min-w-0 flex-1 px-2 pb-1">Concepts they feed, least supported first</div>
              </div>
              <div className="flex" data-health="links">
                <ul className="min-w-0 flex-1">
                  {sources.map((s) => (
                    <li key={s.node.id} style={{ height: ROW }}>
                      <button type="button" data-source={s.node.id} onClick={() => onRead(s.node.id)} title={titleOf(s.node)} {...hover(s.node.id)} className={cn("flex h-full w-full min-w-0 items-center justify-end gap-2 rounded-md px-2 text-right text-[12px] text-foreground transition-opacity hover:bg-accent motion-reduce:transition-none", dim(s.node.id), RING)}>
                        <span className="truncate">{titleOf(s.node)}</span>
                        <SourceIcon type={s.node.type} className="size-3.5 flex-none text-muted-foreground" />
                      </button>
                    </li>
                  ))}
                </ul>
                <svg width={GAP_W} height={height} className="flex-none" aria-hidden>
                  {links.map((l) => {
                    const on = !!lit && lit.has(l.s) && lit.has(l.c) && (hot === l.s || hot === l.c);
                    return (
                      <path
                        key={`${l.s}|${l.c}`}
                        d={`M0 ${y(l.from)}C${GAP_W / 2} ${y(l.from)} ${GAP_W / 2} ${y(l.to)} ${GAP_W} ${y(l.to)}`}
                        fill="none"
                        strokeWidth={on ? 1.25 : 1}
                        className={cn("transition-opacity motion-reduce:transition-none", on ? "stroke-foreground opacity-60" : lit ? "stroke-muted-foreground opacity-10" : "stroke-muted-foreground opacity-30")}
                      />
                    );
                  })}
                </svg>
                <ul className="min-w-0 flex-1">
                  {concepts.map((c) => {
                    const s = supportOf(c.node, support);
                    return (
                      <li key={c.node.id} style={{ height: ROW }}>
                        <button type="button" data-concept={c.node.id} onClick={() => onRead(c.node.id)} title={`${titleOf(c.node)}${s ? `: ${SUPPORT_LABEL[s].toLowerCase()}` : ""}`} {...hover(c.node.id)} className={cn("flex h-full w-full min-w-0 items-center gap-2 rounded-md px-2 text-left text-[12px] text-foreground transition-opacity hover:bg-accent motion-reduce:transition-none", dim(c.node.id), RING)}>
                          <NodeSwatch type={c.node.type} color={colorOf(c.node, "support")} className="size-3.5 flex-none" />
                          <span className="truncate">{titleOf(c.node)}</span>
                          {s && (
                            <span className="ml-auto flex-none pl-2 tabular-nums text-muted-foreground" aria-label={`${c.support} sources`}>
                              {c.support}
                            </span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
              {more > 0 && <p className="px-2 pt-2 text-[11px] text-muted-foreground">{more} more sources in use are not drawn here.</p>}
            </>
          ) : (
            <p className="px-2 py-6 text-[12px] text-muted-foreground">None of these sources feeds a concept yet.</p>
          )}
        </div>
      </div>
    </div>
  );
}
