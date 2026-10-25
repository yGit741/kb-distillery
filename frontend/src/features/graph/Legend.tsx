import { useEffect, useMemo, useRef } from "react";
import { cn } from "@/lib/utils";
import { useTheme } from "@/theme/theme";
import { Swatch } from "./controls";
import { colorKeyRows, LAYER_LABEL, layerGroups, type LayerGroup } from "./legendModel";
import { QUICK_OFF, QUICK_STEPS, type QuickFilters } from "./quickFilters";
import type { GraphSchema } from "./schema";
import { useGraphUi } from "./store";
import { COLOR_BY, effectiveColorBy, MAIL_TYPES, markOf, METRIC_COLORS, neutralRamp, NO_AREA, OTHER_AREAS, RAMP_BY, RAMP_MEANING, RAMP_STEPS, TYPE_LABEL_OVERRIDE, type ColorBy, type NodeMark } from "./style";
import type { GNode } from "./types";

/** A type's mark in the text colour (the canvas `drawMark` in SVG): the mark is the type, so the chip carries no colour. */
function ShapeIcon({ shape }: { shape: NodeMark }) {
  const ring = <circle cx="8" cy="8" r="5.6" fill="none" stroke="currentColor" strokeWidth="1.5" />;
  return (
    <svg viewBox="0 0 16 16" className="size-3.5 shrink-0" aria-hidden>
      {shape === "source" && <circle cx="8" cy="8" r="6" fill="currentColor" />}
      {shape === "person" && (
        <>
          <circle cx="8" cy="8" r="7" fill="currentColor" />
          <text x="8" y="8.6" textAnchor="middle" dominantBaseline="middle" fontSize="6.4" fontWeight="700" className="fill-background">
            GK
          </text>
        </>
      )}
      {shape === "question" && (
        <>
          {ring}
          <text x="8" y="8.8" textAnchor="middle" dominantBaseline="middle" fontSize="7.5" fontWeight="700" fill="currentColor">
            ?
          </text>
        </>
      )}
      {shape === "idea" && (
        <>
          {ring}
          <circle cx="8" cy="8" r="2" fill="currentColor" />
        </>
      )}
      {shape === "topic" && (
        <>
          {ring}
          <path d="M5.6 5.9h4.8M5.6 8h4.8M5.6 10.1h4.8" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
        </>
      )}
      {shape === "collection" && (
        <>
          <circle cx="8" cy="8" r="7.2" fill="none" stroke="currentColor" strokeWidth="0.9" />
          <circle cx="8" cy="8" r="4.6" fill="none" stroke="currentColor" strokeWidth="1.4" />
        </>
      )}
    </svg>
  );
}

/** A source type's icon: the glyph the canvas draws inside a zoomed or hovered source dot. */
function SourceIcon({ type }: { type: string }) {
  const s = { fill: "none", stroke: "currentColor", strokeWidth: 1.3, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 16 16" className="size-3.5 shrink-0" aria-hidden>
      {type === "paper" ? (
        <path d="M4 2h5.5L12 4.5V14H4zM6 8h4M6 10.5h4" {...s} />
      ) : type === "ai-chat" ? (
        <path d="M8 1.8c.4 2.9 1.6 4.8 6.2 6.2-4.6 1.4-5.8 3.3-6.2 6.2-.4-2.9-1.6-4.8-6.2-6.2C6.4 6.6 7.6 4.7 8 1.8z" fill="currentColor" />
      ) : MAIL_TYPES.has(type) ? (
        <path d="M2.5 4h11v8h-11zM2.5 4 8 8.6 13.5 4" {...s} />
      ) : type === "lecture" ? (
        <path d="M5 3.5 12 8l-7 4.5z" fill="currentColor" />
      ) : type === "part" || type === "book" ? (
        <path d="M8 4.5C6.5 3.5 4.5 3.5 2.5 4v8c2-.5 4-.5 5.5.5 1.5-1 3.5-1 5.5-.5V4c-2-.5-4-.5-5.5.5zM8 4.5v8" {...s} />
      ) : (
        <path d="M3 5h10M3 8h10M3 11h6" {...s} />
      )}
    </svg>
  );
}

interface Props {
  nodes: readonly GNode[];
  visible: ReadonlySet<string>;
  schema: GraphSchema;
  shownTypes: ReadonlySet<string> | null;
  stats: string;
  /** pages the one-click filters hide on top of the rest */
  quickHidden?: number;
  /** how many pages are selected */
  selected?: number;
}

/** What the nodes can be coloured by from the legend: the colourings that answer a question about the vault. */
const COLOUR_PICK: readonly ColorBy[] = ["area", "depth", "status", "degree", "evidence"];
const COLOUR_PICK_LABEL: Partial<Record<ColorBy, string>> = { area: "Area", depth: "Depth", status: "Status", degree: "Links", evidence: "Evidence" };

/** The colour key's header: "Colour ·" and the colouring, switchable among the ones that make sense. */
function ColourBy({ by, className }: { by: ColorBy; className?: string }) {
  return (
    <label className={cn("flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground", className)}>
      Colour ·
      <select
        className="rounded border bg-transparent px-1 py-0.5 text-[11px] font-semibold normal-case tracking-normal text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        value={COLOUR_PICK.includes(by) ? by : ""}
        aria-label="Colour by"
        onChange={(e) => useGraphUi.setState({ colorBy: e.target.value as ColorBy, hiddenKeys: new Set(), story: "" })}
      >
        {!COLOUR_PICK.includes(by) && <option value="">{COLOR_BY.find((c) => c.id === by)?.label ?? by}</option>}
        {COLOUR_PICK.map((c) => (
          <option key={c} value={c}>
            {COLOUR_PICK_LABEL[c]}
          </option>
        ))}
      </select>
    </label>
  );
}

/** One quick filter chip: off is a plain chip; on it shows its value with − / + to walk the steps. */
function QuickChip({
  label,
  title,
  value,
  steps,
  unit = "",
  disabled,
  onChange,
}: {
  label: string;
  title: string;
  value: number;
  steps: readonly number[];
  unit?: string;
  disabled?: string;
  onChange: (v: number) => void;
}) {
  const on = value > 0;
  const i = steps.indexOf(value);
  // every chip is one fixed size; when on, its − / + float in a small pill above it, over the canvas, so the
  // row never moves
  return (
    <span className="relative shrink-0">
      <button
        type="button"
        className={cn(CHIP, "w-28 justify-center", on ? "bg-accent-soft text-primary" : "text-muted-foreground", disabled && !on && "opacity-50")}
        aria-pressed={on}
        title={on ? `${title} · click to turn off` : (disabled ?? title)}
        onClick={() => onChange(on ? 0 : steps[Math.min(2, steps.length - 1)]!)}
      >
        {label}
        {on && <b className="font-semibold tabular-nums">{`${value}${unit}`}</b>}
      </button>
      {on && (
        <span className="absolute bottom-full left-1/2 mb-1 flex -translate-x-1/2 items-center rounded-full border bg-card text-primary shadow-[var(--shadow)]">
          <button type="button" className="px-2 text-sm leading-5 hover:bg-accent disabled:opacity-30" aria-label={`${label}: less`} disabled={i <= 0} onClick={() => onChange(steps[i - 1]!)}>
            −
          </button>
          <button type="button" className="border-l px-2 text-sm leading-5 hover:bg-accent disabled:opacity-30" aria-label={`${label}: more`} disabled={i >= steps.length - 1} onClick={() => onChange(steps[i + 1]!)}>
            +
          </button>
        </span>
      )}
    </span>
  );
}

const CHIP = "flex shrink-0 items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs hover:bg-accent";
const GROUP = "shrink-0 rounded-md px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground hover:bg-accent hover:text-foreground";
const PANEL = "pointer-events-auto rounded-lg border bg-card/95 shadow-[var(--shadow)]";
/** The legend's hover settles before it spotlights, and lingers a little on the way out (the canvas fade does the rest). */
const SPOT_IN_MS = 120;
const SPOT_OUT_MS = 160;
/** Concepts first (what I think with), then collections, then sources (what I read). */
const LAYER_ORDER = ["concept", "collection", "source"] as const;

/**
 * The legend, bottom-left, in two rows. Above: the filters (Concepts only, Show all, "+" for a rule of your own).
 * Below: the key in two groups ("Concepts: … | Sources: …", collections folded into sources), each type with its mark
 * (sources with their glyph). A group name hides or shows the whole layer, a type hides or shows itself, and
 * hovering either spotlights its pages on the canvas through the hover fade. Top-right, the colour key is the
 * view's: the colouring's values (a click hides or shows one), or a stepped bar for an ordered colouring.
 */
export function Legend({ nodes, visible, schema, shownTypes, stats, quickHidden = 0 }: Props) {
  const ui = useGraphUi();
  const theme = useTheme((s) => s.theme);
  const groups = useMemo(() => layerGroups(nodes, visible, schema, shownTypes), [nodes, visible, schema, shownTypes]);
  const by = effectiveColorBy(ui.colorBy, ui.shapes);
  const ramp = ui.shapes && RAMP_BY.has(by) ? theme : null;
  // every page the type filter lets through, so a value hidden by the key stays listed (and can be shown again)
  const keyPool = useMemo(() => {
    if (!ui.hiddenKeys.size) return visible;
    const pool = new Set(visible);
    for (const n of nodes) if (!shownTypes || shownTypes.has(n.type)) pool.add(n.id);
    return pool;
  }, [nodes, visible, shownTypes, ui.hiddenKeys]);
  const key = useMemo(() => (by === "type" ? [] : colorKeyRows(nodes, keyPool, by, 12, ramp)), [nodes, keyPool, by, ramp]);
  const allTypes = useMemo(() => groups.flatMap((g) => g.rows.map((r) => r.id)), [groups]);
  const defaults = schema.defaultVisible;
  const hullsOn = ui.shapes && by !== "area";
  // two groups in the key: concepts, and sources with the collections folded in (courses, books, series are read too)
  const ordered = useMemo((): LayerGroup[] => {
    const concept = groups.find((g) => g.layer === "concept");
    const read = LAYER_ORDER.filter((l) => l !== "concept").flatMap((l) => groups.find((g) => g.layer === l)?.rows ?? []);
    const on = read.filter((r) => r.shown).length;
    const source: LayerGroup | null = read.length
      ? { layer: "source", rows: read, total: read.reduce((s, r) => s + r.total, 0), state: on === 0 ? "none" : on === read.length ? "all" : "some" }
      : null;
    return [concept, source].filter((g): g is LayerGroup => !!g);
  }, [groups]);
  const filtered = ui.rules.length > 0;
  const q = ui.quick;
  const setQuick = (patch: Partial<QuickFilters>) => useGraphUi.setState({ quick: { ...q, ...patch }, story: "" });

  // spotlight: settle in, linger out; the canvas fades through its hover fade either way
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const spot = (types: readonly string[] | null) => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => useGraphUi.setState({ spotlight: types ? new Set(types) : null }), types ? SPOT_IN_MS : SPOT_OUT_MS);
  };
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      useGraphUi.setState({ spotlight: null });
    },
    [],
  );

  return (
    <section aria-label="Legend" data-tour="graph-legend" title={stats} className="contents">
      <div className="pointer-events-none absolute bottom-3 left-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-col items-start gap-1.5">
        {/* the filters: two presets and "+" for a rule of your own (the Filters panel) */}
        <div className={cn(PANEL, "flex items-center gap-0.5 px-1 py-0.5")} role="group" aria-label="Filters">
          <button type="button" className={cn(CHIP, "text-muted-foreground")} title="The concept layer: topics, ideas and questions" onClick={() => useGraphUi.setState({ shownTypes: undefined, predicate: null, story: "" })}>
            Concepts only
          </button>
          <button type="button" className={cn(CHIP, "text-muted-foreground")} onClick={() => useGraphUi.setState({ shownTypes: null, predicate: null, story: "", quick: QUICK_OFF })}>
            Show all
          </button>
          <span className="mx-0.5 h-4 border-l" aria-hidden />
          <QuickChip
            label="Recent"
            unit="d"
            title="Only pages added in the last N days"
            value={q.recent}
            steps={QUICK_STEPS.recent}
            onChange={(v) => setQuick({ recent: v })}
          />
          <QuickChip
            label="Connected"
            unit="+"
            title="Only pages with at least N links among those shown (drops orphans and dead ends)"
            value={q.connected}
            steps={QUICK_STEPS.connected}
            onChange={(v) => setQuick({ connected: v })}
          />
          {quickHidden > 0 && <small className="px-1 text-muted-foreground" title="Pages these filters hide">−{quickHidden}</small>}
          <button
            type="button"
            className={cn(CHIP, "border-l px-2 text-muted-foreground", filtered && "text-primary")}
            aria-label="Add a filter"
            title={filtered ? `Filters (${ui.rules.length} active): add or edit` : "Add a filter of your own"}
            onClick={() => {
              useGraphUi.setState({ railOpen: false });
              ui.openFlyout("filter");
            }}
          >
            +{filtered ? ` ${ui.rules.length}` : ""}
          </button>
        </div>
        {/* the key wraps onto a second line rather than cutting a type off */}
        <div className={cn(PANEL, "flex min-w-0 max-w-full flex-wrap items-center gap-x-1 gap-y-0.5 px-1.5 py-1")} onMouseLeave={() => spot(null)}>
          {ordered.map((g) => (
            <div key={g.layer} className="flex flex-wrap items-center gap-0.5 border-r pr-1 last:border-r-0">
              <button
                type="button"
                className={cn(GROUP, g.state === "none" && "opacity-40")}
                aria-pressed={g.state !== "none"}
                title={g.state === "none" ? `Show every ${g.layer}` : `Hide every ${g.layer}`}
                onMouseEnter={() => spot(g.rows.map((r) => r.id))}
                onClick={() => ui.setLayerTypes(g.rows.map((r) => r.id), g.state === "none", allTypes, defaults)}
              >
                {LAYER_LABEL[g.layer]}:
              </button>
              {g.rows.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  className={cn(CHIP, !r.shown && "opacity-40")}
                  aria-pressed={r.shown}
                  title={`${r.shown ? "Hide" : "Show"} every ${(TYPE_LABEL_OVERRIDE[r.id] ?? r.label).toLowerCase()}`}
                  onMouseEnter={() => spot([r.id])}
                  onFocus={() => spot([r.id])}
                  onBlur={() => spot(null)}
                  onClick={() => ui.toggleType(r.id, allTypes, defaults)}
                >
                  {r.layer === "source" ? <SourceIcon type={r.id} /> : <ShapeIcon shape={markOf(r.id)} />}
                  <span>{TYPE_LABEL_OVERRIDE[r.id] ?? r.label}</span>
                  <small className="text-muted-foreground">{r.total}</small>
                </button>
              ))}
            </div>
          ))}
        </div>
        <span className="sr-only" data-testid="graph-stats">
          {stats}
        </span>
      </div>
      {ramp && RAMP_MEANING[by] && (
        <aside aria-label="Colour key" className={cn(PANEL, "absolute right-3 top-14 z-10 flex w-60 flex-col gap-1.5 p-2")}>
          <ColourBy by={by} />
          <div className="text-xs leading-snug">{RAMP_MEANING[by]!.what}</div>
          {METRIC_COLORS.has(by) ? (
            // a continuous signal: the five steps the nodes snap to, light to dark
            <div className="flex h-3 overflow-hidden rounded-sm border" aria-hidden>
              {Array.from({ length: RAMP_STEPS }, (_, i) => (
                <i key={i} className="flex-1" style={{ background: neutralRamp(i / (RAMP_STEPS - 1), ramp === "dark") }} />
              ))}
            </div>
          ) : (
            // ordered values: one segment each, as wide as its share, a click hides or shows it
            <div className="flex gap-px overflow-hidden rounded-sm">
              {key.map((r) => {
                const hidden = ui.hiddenKeys.has(r.label);
                return (
                  <button
                    key={r.label}
                    type="button"
                    className={cn("flex min-w-6 flex-col items-stretch gap-0.5 text-left", hidden && "opacity-30")}
                    style={{ flex: `${Math.max(1, Math.sqrt(r.count))} 1 0` }}
                    aria-pressed={!hidden}
                    title={`${hidden ? "Show" : "Hide"} ${r.label} (${r.count})`}
                    onClick={() => ui.toggleKey(r.label)}
                  >
                    <i className="block h-3" style={{ background: r.color }} />
                    <span className="truncate text-[10px] leading-tight">{r.label}</span>
                    <small className="text-[10px] leading-tight text-muted-foreground">{r.count}</small>
                  </button>
                );
              })}
            </div>
          )}
          <div className="flex justify-between text-[10px] text-muted-foreground">
            <span>{RAMP_MEANING[by]!.low}</span>
            <span>{RAMP_MEANING[by]!.high}</span>
          </div>
          {hullsOn && <div className="border-t pt-1 text-[10px] text-muted-foreground">Tinted regions: themes (area)</div>}
        </aside>
      )}
      {key.length > 0 && !(ramp && RAMP_MEANING[by]) && (
        <aside aria-label="Colour key" className={cn(PANEL, "absolute right-3 top-14 z-10 flex max-h-[calc(100%-8rem)] w-44 flex-col gap-0.5 overflow-y-auto p-1.5")}>
          <ColourBy by={by} className="px-1 pb-0.5" />
          {key.map((r) => {
            const hidden = ui.hiddenKeys.has(r.label);
            return (
              <button
                key={r.label}
                type="button"
                className={cn(CHIP, "w-full justify-start text-left", hidden && "opacity-40")}
                aria-pressed={!hidden}
                title={`${hidden ? "Show" : "Hide"} ${r.label}`}
                onClick={() => ui.toggleKey(r.label)}
              >
                {r.label === NO_AREA ? (
                  // "No area" is the faint grey: a ring in the key so it never reads as "Other areas"
                  <i aria-hidden className="inline-block size-2.5 shrink-0 rounded-full border-2" style={{ borderColor: r.color }} />
                ) : (
                  <Swatch color={r.color} className={cn("size-2.5", ramp && "rounded-sm")} />
                )}
                <span className={cn("min-w-0 truncate", (r.label === NO_AREA || r.label === OTHER_AREAS) && "italic text-muted-foreground")}>{r.label}</span>
                <small className="ml-auto pl-1 text-muted-foreground">{r.count}</small>
              </button>
            );
          })}
          {hullsOn && <div className="border-t px-1 pt-1 text-[10px] text-muted-foreground">Tinted regions: themes (area)</div>}
        </aside>
      )}
    </section>
  );
}
