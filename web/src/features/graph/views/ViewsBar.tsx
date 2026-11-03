import { ChevronDown, Info, Sigma, X } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useFlag } from "@/flags/useFlag";
import { cn } from "@/lib/utils";
import { spectrum, type Spectrum } from "../directions/fourier";
import { shortTheme, useCached, useDirectionsCache } from "../directions/ui";
import { HEADLINE_STORIES, MORE_STORIES, storyById, storyOffered } from "../lab/views";
import { useGraphUi } from "../store";
import { useDecor, type Arc } from "../tools/decor";
import type { GraphModel } from "../types";
import { explainOf } from "./explain";

export const VIEWS_BAR_ID = "graph-views";
/** chords drawn: every positive level-2 coefficient, and the pairs most below chance (dashed) */
const MAX_ARCS = 12;
const MAX_APART = 6;
/** our own cache slot: the Fourier panel keys its slot by its options and the two must not evict each other */
const SLOT = "fourier-views";
const SPECTRUM_KEY = "views";

interface Props {
  model: GraphModel;
  visible: ReadonlySet<string>;
  /** Apply a story by id (the screen also updates the URL and the story's seed view or tool). */
  onPick: (id: string) => void;
}

/**
 * Chords for the spectrum between the pinned theme pages: solid = themes the notes treat together more than
 * chance (positive correlation, width ∝ coefficient); dashed = big pairs that meet less than chance.
 */
export function spectrumArcs(model: GraphModel, s: Spectrum, max = MAX_ARCS, maxApart = MAX_APART): Arc[] {
  const topicOf = new Map<string, string>();
  for (const n of model.nodes) if (n.type === "topic" && n.areas[0] && !topicOf.has(n.areas[0])) topicOf.set(n.areas[0], n.id);
  const known = s.pairs.filter((p) => topicOf.has(p.a) && topicOf.has(p.b));
  const pos = known.filter((p) => p.coef > 0 && p.both >= 2).sort((a, b) => b.coef - a.coef).slice(0, max);
  const top = pos[0]?.coef || 1;
  const apart = known.filter((p) => p.coef < 0 && p.expected >= 3 && p.both < p.expected / 2).sort((a, b) => a.coef - b.coef).slice(0, maxApart);
  const low = apart[0]?.coef || -1;
  return [
    ...pos.map((p) => ({ a: topicOf.get(p.a) as string, b: topicOf.get(p.b) as string, w: p.coef / top })),
    ...apart.map((p) => ({ a: topicOf.get(p.a) as string, b: topicOf.get(p.b) as string, w: p.coef / low, apart: true })),
  ];
}

const PILL = "rounded-full px-3 py-1 text-sm transition-colors";

/**
 * The views bar, top-centre of the graph: three headline views as pills (Map, Thesis, Explore), "More" for the
 * rest, Σ to draw the theme spectrum in Map, and ⓘ for how the active view is computed. Hovering a pill shows
 * the questions that view answers. No pill is lit once a knob was changed by hand (the view is "custom");
 * clicking one applies it again.
 */
export function ViewsBar({ model, visible, onPick }: Props) {
  const story = useGraphUi((s) => s.story);
  useFlag("research-tools"); // re-render when the flag lands: it decides which views are offered
  const [more, setMore] = useState(false);
  const [info, setInfo] = useState(false);
  const [sigma, setSigma] = useState(false);
  const active = storyById(story);
  const isMap = story === "map";

  // ---- the spectrum chords (Map only)
  const cached = useCached<Spectrum>(SLOT, model, SPECTRUM_KEY);
  useEffect(() => {
    if (!isMap || !sigma || cached) return;
    const t = window.setTimeout(() => useDirectionsCache.getState().put(SLOT, { model, key: SPECTRUM_KEY, value: spectrum(model) }), 0);
    return () => window.clearTimeout(t);
  }, [isMap, sigma, cached, model]);
  const arcs = useMemo(() => (isMap && sigma && cached ? spectrumArcs(model, cached) : null), [isMap, sigma, cached, model]);
  useEffect(() => {
    useDecor.getState().setArcs(arcs);
    return () => useDecor.getState().setArcs(null);
  }, [arcs]);

  const explain = active ? explainOf(active.id) : undefined;
  const links = model.links.length;
  const themes = model.nodes.filter((n) => n.type === "topic").length;
  const solid = arcs?.filter((a) => !a.apart).length ?? 0;
  const dashed = (arcs?.length ?? 0) - solid;
  const topPairs = cached && sigma ? [...cached.pairs].filter((p) => p.coef > 0).sort((a, b) => b.coef - a.coef).slice(0, 3) : [];

  return (
    <div id={VIEWS_BAR_ID} data-tour="graph-views" className="pointer-events-auto absolute left-1/2 top-3 z-20 flex -translate-x-1/2 items-center gap-0.5 rounded-full border bg-card/95 p-0.5 shadow-[var(--shadow)]">
      {HEADLINE_STORIES.filter(storyOffered).map((s) => {
        const on = story === s.id;
        return (
          <button
            key={s.id}
            type="button"
            className={cn(PILL, on ? "bg-accent-soft font-medium text-primary" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground")}
            aria-pressed={on}
            title={`${s.headline?.goal}\n\n${s.headline?.questions.join("\n")}\n— ${s.headline?.hint}`}
            onClick={() => onPick(s.id)}
          >
            {s.headline?.label}
          </button>
        );
      })}
      <div className="relative">
        <button
          type="button"
          className={cn(PILL, "flex items-center gap-0.5", active && !active.headline ? "bg-accent-soft font-medium text-primary" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground")}
          aria-haspopup="menu"
          aria-expanded={more}
          title="Other views"
          onClick={() => setMore(!more)}
          onBlur={() => window.setTimeout(() => setMore(false), 120)}
          onKeyDown={(e) => e.key === "Escape" && setMore(false)}
        >
          {active && !active.headline ? active.name.split(":")[0] : "More"}
          <ChevronDown aria-hidden className="size-3.5" />
        </button>
        {more && (
          <ul role="menu" aria-label="Other views" className="absolute left-0 top-full z-30 mt-1 w-56 rounded-lg border bg-popover p-1 text-sm shadow-[var(--shadow)]" onMouseDown={(e) => e.preventDefault()}>
            {MORE_STORIES.filter(storyOffered).map((s) => (
              <li key={s.id} role="none">
                <button
                  type="button"
                  role="menuitem"
                  className={cn("block w-full rounded-md px-2 py-1 text-left hover:bg-accent", story === s.id && "bg-accent-soft text-primary")}
                  title={s.story}
                  onClick={() => {
                    setMore(false);
                    onPick(s.id);
                  }}
                >
                  {s.name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
      {!active && <span className="px-2 text-xs text-muted-foreground" title="A setting was changed by hand; click a view to apply it again">custom</span>}
      {isMap && (
        <Button
          variant={sigma ? "secondary" : "ghost"}
          size="icon"
          className={cn("size-7 rounded-full", sigma && "bg-accent-soft text-primary")}
          aria-pressed={sigma}
          aria-label="Theme spectrum: chords between themes the notes treat together"
          title="Theme spectrum (Σ): solid chords = themes the notes treat together more than chance; dashed = big pairs that never meet"
          onClick={() => setSigma(!sigma)}
        >
          <Sigma aria-hidden />
        </Button>
      )}
      <Button variant="ghost" size="icon" className="size-7 rounded-full" aria-label="How this view is computed" title="How this view is computed" disabled={!explain} onClick={() => setInfo(true)}>
        <Info aria-hidden />
      </Button>
      <Dialog open={info && !!explain} onOpenChange={setInfo}>
        <DialogContent className="max-h-[85vh] overflow-y-auto p-5 sm:max-w-lg">
          <div className="flex items-start justify-between gap-3">
            <DialogTitle className="text-base font-semibold">{active?.headline?.label ?? active?.name}: how it is computed</DialogTitle>
            <Button variant="ghost" size="icon" className="-mr-2 -mt-2 size-7 shrink-0" aria-label="Close" onClick={() => setInfo(false)}>
              <X aria-hidden />
            </Button>
          </div>
          <DialogDescription className="mb-3 mt-1 text-sm text-muted-foreground">{active?.story}</DialogDescription>
          {explain && (
            <dl className="flex flex-col gap-3 text-sm">
              <Row k="Now">
                {visible.size} of {model.nodes.length} pages drawn · {links} links · {themes} themes
                {isMap && sigma && cached ? ` · Σ over ${cached.n} themed pages: ${solid} solid chord${solid === 1 ? "" : "s"}, ${dashed} dashed` : ""}
              </Row>
              <Row k="Pages">{explain.filters}</Row>
              <Row k="Layout">{explain.layout}</Row>
              <Row k="Labels">{explain.ranking}</Row>
              <Row k="Algorithms">
                {explain.algorithms.length ? (
                  <ul className="flex flex-col gap-1.5">
                    {explain.algorithms.map((a) => (
                      <li key={a.name}>
                        <b>{a.name}.</b> {a.what}
                      </li>
                    ))}
                  </ul>
                ) : (
                  "None: filter and layout only."
                )}
              </Row>
              {topPairs.length > 0 && (
                <Row k="Strongest pairs">
                  <ul className="tabular-nums">
                    {topPairs.map((p) => (
                      <li key={`${p.a}|${p.b}`}>
                        {shortTheme(p.a)} × {shortTheme(p.b)}: {p.coef.toFixed(2)} ({p.both} pages together, {p.expected.toFixed(1)} expected)
                      </li>
                    ))}
                  </ul>
                </Row>
              )}
            </dl>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Row({ k, children }: { k: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{k}</dt>
      <dd className="mt-0.5 text-foreground/90">{children}</dd>
    </div>
  );
}
