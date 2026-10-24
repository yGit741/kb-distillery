import { PanelLeftClose } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { typeColor } from "@/theme/palette";
import { CheckField, RangeField, SelectField, Swatch } from "../controls";
import { useGraphUi } from "../store";
import { COLOR_BY, SIZE_BY } from "../style";
import type { GNode } from "../types";
import type { LabConfig } from "./config";
import { useLabHud } from "./hud";
import { TERM_WEIGHTS, type Importance } from "./importance";
import { STORIES, storyById } from "./views";

type Opt<T extends string> = readonly { id: T; label: string }[];
type Knob =
  | { kind: "range"; key: keyof LabConfig; label: string; min: number; max: number; step: number; hint?: string; show?: (c: LabConfig) => boolean }
  | { kind: "select"; key: keyof LabConfig; label: string; options: Opt<string>; hint?: string; show?: (c: LabConfig) => boolean }
  | { kind: "check"; key: keyof LabConfig; label: string; hint?: string; show?: (c: LabConfig) => boolean };

const range = (key: keyof LabConfig, label: string, min: number, max: number, step: number, o: { hint?: string; show?: (c: LabConfig) => boolean } = {}): Knob => ({ kind: "range", key, label, min, max, step, ...o });
const select = (key: keyof LabConfig, label: string, options: Opt<string>, o: { hint?: string; show?: (c: LabConfig) => boolean } = {}): Knob => ({ kind: "select", key, label, options, ...o });
const check = (key: keyof LabConfig, label: string, o: { hint?: string; show?: (c: LabConfig) => boolean } = {}): Knob => ({ kind: "check", key, label, ...o });

const tiersShown = (c: LabConfig) => c.sizeMode === "tiers" || c.sizeMode === "quantile";

/** The lab's sections, in its order. Each knob writes the rail config; changing one turns the view "custom". */
const SECTIONS: readonly { title: string; open?: boolean; knobs: readonly Knob[] }[] = [
  {
    title: "Importance score",
    open: true,
    knobs: [
      range("wTier", "Type tier", 0, 2, 0.1, { hint: "topic > question > idea > person > collection > paper > article" }),
      range("wEvidence", "Evidence (digested sources)", 0, 2, 0.1, { hint: "neighbouring sources weighted by depth: easy·w, full 2, deep 3" }),
      range("easyWeight", "…weight of an easy skim", 0, 1, 0.1),
      range("wDegree", "Link count", 0, 2, 0.1, { hint: "log scale; inflated by bulk imports" }),
      select("degBasis", "Count links in", [
        { id: "visible", label: "the visible graph" },
        { id: "nohub", label: "the visible graph, minus collection links" },
        { id: "all", label: "the whole vault" },
      ]),
      range("wPagerank", "Centrality (PageRank)", 0, 2, 0.1),
      range("wBetween", "Bridge (betweenness)", 0, 2, 0.1, { hint: "pages on the shortest paths between clusters" }),
      range("wOpen", "Open question bonus", 0, 2, 0.1),
      range("wGap", "Thin spot / reading value", 0, 2, 0.1, { hint: "concepts: many links, little evidence; sources: many links, read shallowly" }),
      range("wOrphan", "Orphan (≤ 1 visible link)", 0, 2, 0.1),
      select("norm", "Normalise each signal", [
        { id: "type", label: "within its type (percentile)" },
        { id: "global", label: "across all visible pages" },
      ]),
    ],
  },
  {
    title: "Which labels show",
    open: true,
    knobs: [
      select("scope", "Choose labels from", [
        { id: "world", label: "the whole graph (panning never changes labels)" },
        { id: "screen", label: "what is on screen (re-picks on every pan)" },
      ]),
      select("strategy", "Budget", [
        { id: "coverage", label: "screen coverage (% of the canvas)" },
        { id: "count", label: "fixed count, grows with zoom" },
        { id: "threshold", label: "score threshold, drops with zoom" },
        { id: "all", label: "everything that fits" },
      ]),
      range("coverage", "Coverage budget %", 2, 40, 1, { show: (c) => c.strategy === "coverage" }),
      range("count", "Count at fit zoom", 3, 80, 1, { show: (c) => c.strategy === "count" }),
      range("threshold", "Score threshold", 0, 1, 0.01, { show: (c) => c.strategy === "threshold" }),
      range("zoomGrowth", "Growth with zoom (exponent)", 0, 2, 0.05, { hint: "labels on screen ∝ zoom^g; 0.5 = radical law (2× zoom → 1.4× labels)", show: (c) => c.strategy !== "all" }),
      select("pool", "Pool", [
        { id: "all", label: "every visible page" },
        { id: "hubs", label: "hubs only until 2× zoom (old rule)" },
      ]),
      check("hoverNeighbors", "Hover labels the neighbours"),
      range("neighborCap", "Neighbours labelled on hover/select", 0, 80, 1, { hint: "top by score; ≈20 is the practical maximum (Fekete & Plaisant)" }),
      check("lens", "Hover lens (excentric labels)", { hint: "lists every page under the pointer in a column with leader lines" }),
      range("lensR", "Lens radius px", 30, 200, 5, { show: (c) => c.lens }),
      range("lensMax", "Lens max labels", 5, 40, 1, { show: (c) => c.lens }),
    ],
  },
  {
    title: "Focus (degree of interest)",
    knobs: [
      range("doiHops", "On select, fade pages beyond hops", 0, 3, 1, { hint: "0 = off. Furnas: interest = importance − distance from the focus" }),
      range("doiLambda", "Penalty per hop", 0, 1, 0.05, { show: (c) => c.doiHops > 0 }),
    ],
  },
  {
    title: "Placement",
    knobs: [
      check("declutter", "Drop labels that would overlap"),
      select("positions", "Candidate positions per label", [
        { id: "1", label: "1 · below (old rule)" },
        { id: "4", label: "4 · above, below, right, left" },
        { id: "8", label: "8 · plus diagonals" },
      ]),
      check("avoidNodes", "Labels avoid covering nodes"),
      range("pad", "Padding px", 0, 10, 1),
    ],
  },
  {
    title: "Typography",
    knobs: [
      select("sizeMode", "Label size", [
        { id: "tiers", label: "3 tiers by type" },
        { id: "quantile", label: "3 tiers by score" },
        { id: "continuous", label: "continuous by score" },
        { id: "uniform", label: "one size" },
      ]),
      range("base", "Uniform / continuous base px", 7, 18, 0.5, { show: (c) => !tiersShown(c) }),
      range("t1", "Tier 1 px (topics, collections)", 8, 24, 0.5, { show: tiersShown }),
      range("t2", "Tier 2 px (ideas, questions, people)", 7, 20, 0.5, { show: tiersShown }),
      range("t3", "Tier 3 px (sources)", 6, 16, 0.5, { show: tiersShown }),
      range("zoomScale", "Labels grow with zoom", 0, 1, 0.05, { hint: "0 = constant on screen (maps); 1 = scale with the drawing" }),
      range("minPx", "Never smaller than px", 2.5, 12, 0.5),
      check("weightTier", "Bold tier 1, muted tier 3"),
      select("textField", "Text", [
        { id: "short", label: "short title" },
        { id: "title", label: "full title" },
        { id: "slug", label: "slug" },
      ]),
      range("maxChars", "Cut at characters", 10, 80, 1),
      select("bg", "Background", [
        { id: "halo", label: "halo" },
        { id: "box", label: "box" },
        { id: "none", label: "none" },
      ]),
    ],
  },
  {
    title: "Stability while moving",
    knobs: [
      range("fade", "Fade ms", 0, 600, 20),
      range("hysteresis", "Keep shown labels (bonus)", 0, 0.6, 0.01, { hint: "a label already on screen beats a slightly better newcomer" }),
    ],
  },
  {
    title: "Region labels (semantic zoom)",
    knobs: [
      select("regions", "Region labels", [
        { id: "off", label: "off" },
        { id: "auto", label: "when zoomed out" },
        { id: "with", label: "always, under page labels" },
      ]),
      range("regionZoom", "Zoomed out means below ×", 0.3, 3, 0.1, { show: (c) => c.regions === "auto" }),
      check("regionsSuppress", "While regions show, only hover and selection get page labels", { show: (c) => c.regions === "auto" }),
      check("hulls", "Shade each theme's region", { hint: "common region groups more strongly than proximity (Palmer)" }),
    ],
  },
];

const fmt = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(2).replace(/0$/, ""));

function Section({ title, open, children }: { title: string; open?: boolean; children: ReactNode }) {
  return (
    <details open={open} className="group border-b py-1.5">
      <summary className="flex cursor-pointer list-none items-center justify-between py-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
        <span aria-hidden className="font-mono group-open:hidden">+</span>
        <span aria-hidden className="hidden font-mono group-open:inline">–</span>
      </summary>
      <div className="flex flex-col gap-2.5 pb-1.5 pt-1">{children}</div>
    </details>
  );
}

function KnobField({ knob, cfg }: { knob: Knob; cfg: LabConfig }) {
  const setLab = useGraphUi((s) => s.setLab);
  const v = cfg[knob.key];
  const set = (val: unknown) => setLab({ [knob.key]: val } as Partial<LabConfig>);
  let field: ReactNode;
  if (knob.kind === "range") field = <RangeField label={knob.label} value={Number(fmt(v as number))} min={knob.min} max={knob.max} step={knob.step} onChange={set} />;
  else if (knob.kind === "select")
    field = <SelectField label={knob.label} value={String(v)} options={knob.options} onChange={(x) => set(/^\d+$/.test(x) ? Number(x) : x)} />;
  else field = <CheckField label={knob.label} checked={Boolean(v)} onChange={set} />;
  return (
    <div className="flex flex-col gap-0.5">
      {field}
      {knob.hint && <p className="text-[11px] leading-snug text-muted-foreground/80">{knob.hint}</p>}
    </div>
  );
}

function WhyRank({ node, imp, cfg }: { node: GNode; imp: Importance; cfg: LabConfig }) {
  const t = imp.terms.get(node.id);
  const s = imp.score.get(node.id);
  if (!t || s === undefined) return <p className="text-xs text-muted-foreground">Not on the graph right now.</p>;
  const rank = [...imp.score.entries()].filter(([, x]) => x > s).length + 1;
  return (
    <div className="flex flex-col gap-1 text-xs">
      <div className="flex items-center gap-1.5 font-medium">
        <Swatch color={typeColor(node.type)} /> <span className="truncate">{node.title || node.id}</span>
      </div>
      <table className="w-full font-mono text-[11px]">
        <tbody>
          {TERM_WEIGHTS.filter(([, w]) => (cfg[w] as number) > 0).map(([k, w]) => (
            <tr key={k}>
              <td className="py-0.5 pr-2">{k}</td>
              <td className="w-2/5">
                <div className="h-1 rounded bg-border">
                  <div className="h-1 rounded bg-primary" style={{ width: `${Math.round(t[k] * 100)}%` }} />
                </div>
              </td>
              <td className="pl-2 text-right">
                {t[k].toFixed(2)} ×{fmt(cfg[w] as number)}
              </td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td className="pt-1">score</td>
            <td />
            <td className="pt-1 text-right">{s.toFixed(3)}</td>
          </tr>
        </tbody>
      </table>
      <p className="text-muted-foreground">
        Rank {rank} of {imp.score.size} drawn pages.
      </p>
    </div>
  );
}

function Hud() {
  const h = useLabHud();
  const cell = (label: string, value: string, warn = false) => (
    <span>
      {label} <b className={cn("font-semibold text-foreground", warn && "text-destructive")}>{value}</b>
    </span>
  );
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-0.5 border-t px-3 py-2 font-mono text-[11px] text-muted-foreground" data-testid="label-hud">
      {cell("zoom", `${h.zoom.toFixed(2)}×`)}
      {cell("labels", `${h.labels}/${h.onScreen}`)}
      {cell("concepts", `${h.concepts}/${h.conceptsVisible}`)}
      {cell("coverage", `${h.coverage.toFixed(1)}%`)}
      {cell("dropped", String(h.dropped))}
      {cell("churn", `${h.churn.toFixed(1)}/s`, h.churn > 8)}
      {cell("smallest", Number.isFinite(h.minPx) ? `${h.minPx.toFixed(1)}px` : "—")}
    </div>
  );
}

/**
 * The left rail (ported from the Label Lab): a view (user story) at the top, what is on the graph (the legend),
 * the label knobs, nodes and links, why the selected page ranks where it does, and live readouts.
 */
export function LabRail({ legend, imp, selected, className }: { legend: ReactNode; imp: Importance; selected: readonly GNode[]; className?: string }) {
  const ui = useGraphUi();
  const cfg = ui.lab;
  const story = storyById(ui.story);
  return (
    <aside aria-label="Labels and views" className={cn("pointer-events-auto flex min-h-0 flex-col border-r bg-card/95 text-sm shadow-[var(--shadow)]", className)}>
      <header className="flex items-center gap-2 border-b px-3 py-2">
        <h2 className="flex-1 text-sm font-semibold">Labels &amp; views</h2>
        <Button variant="ghost" size="icon" className="size-7" aria-label="Hide the rail" title="Hide the rail" onClick={() => ui.set({ railOpen: false })}>
          <PanelLeftClose aria-hidden />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-4">
        <Section title="View · user story" open>
          <SelectField
            label="Start from"
            value={ui.story}
            options={[...STORIES.map((s) => ({ id: s.id, label: s.name })), { id: "", label: "Custom" }]}
            onChange={(id) => (id ? ui.applyStory(id) : ui.set({ story: "" }))}
          />
          {story && (
            <p className="rounded-md bg-accent-soft px-2.5 py-2 text-xs leading-relaxed">
              <b className="block">{story.name}</b>
              {story.story}
            </p>
          )}
        </Section>
        <Section title="What is on the graph" open>
          {legend}
          <SelectField
            label="Layout"
            value={ui.layoutMode}
            options={[
              { id: "anchored", label: "themes anchored on a ring (map-like)" },
              { id: "free", label: "free force layout" },
            ]}
            onChange={(layoutMode) => ui.set({ layoutMode, story: "" })}
          />
          {ui.layoutMode === "anchored" && <RangeField label="Pull toward own theme" value={ui.areaPull} min={0} max={0.3} step={0.01} onChange={(areaPull) => ui.set({ areaPull })} />}
        </Section>
        {SECTIONS.map((sec) => (
          <Section key={sec.title} title={sec.title} open={sec.open}>
            {sec.knobs.filter((k) => !k.show || k.show(cfg)).map((k) => <KnobField key={k.key} knob={k} cfg={cfg} />)}
          </Section>
        ))}
        <Section title="Nodes & links">
          <SelectField label="Node size" value={ui.sizeBy} options={SIZE_BY} onChange={(sizeBy) => ui.set({ sizeBy, story: "" })} />
          <RangeField label="Base size" value={ui.nodeSize} min={2} max={12} step={0.5} onChange={(nodeSize) => ui.set({ nodeSize })} />
          <KnobField knob={range("nodeRange", "Size range", 0, 5, 0.1)} cfg={cfg} />
          <KnobField knob={check("perceptual", "Perceptual scaling (r ∝ v^0.57)", { hint: "people underestimate area; Flannery's correction" })} cfg={cfg} />
          <SelectField label="Colour" value={ui.colorBy} options={COLOR_BY} onChange={(colorBy) => ui.set({ colorBy, story: "" })} />
          <RangeField label="Link opacity" value={ui.linkOpacity} min={0.05} max={0.9} step={0.05} onChange={(linkOpacity) => ui.set({ linkOpacity })} />
          <CheckField label="Directional arrows" checked={ui.arrows} onChange={(arrows) => ui.set({ arrows })} />
          <CheckField label="Highlight neighbourhood" checked={ui.highlight} onChange={(highlight) => ui.set({ highlight })} hint="Dim everything but the hovered or selected pages and their neighbours" />
          <CheckField label="Magnetic pointer" checked={ui.magnet} onChange={(magnet) => ui.set({ magnet })} hint="Hover takes the nearest page; how far it reaches follows how crowded the graph is around it" />
        </Section>
        {selected.length === 1 && selected[0] && (
          <Section title="Why this rank" open>
            <WhyRank node={selected[0]} imp={imp} cfg={cfg} />
          </Section>
        )}
      </div>
      <Hud />
    </aside>
  );
}
