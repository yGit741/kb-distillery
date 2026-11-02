import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { areaColor } from "@/theme/palette";
import { CheckField, RangeField, SelectField } from "../controls";
import type { GraphToolContext } from "../tools";
import { useDecor } from "../tools/decor";
import { influence, type Influence } from "./influence";
import { heldAt, linkKey, thresholds, type PairThreshold, type ThresholdResult } from "./threshold";
import { MiniChart, num, pct, Section, shortTheme, Story, ThemeChip, useCached, useDecorLifetime, useDirectionsCache } from "./ui";

const OWNER = "directions-threshold";
const GRID = Array.from({ length: 51 }, (_, i) => i / 50);

/**
 * Sharp thresholds (experiment "threshold"): the p slider keeps each link with probability p (one fixed
 * draw, so moving it right only ever adds links) and the panel shows, over many draws, at which p each
 * theme holds together and how sharply. A theme's hinge is the page that most often tips it over; a page's
 * influence (KKL) is how often removing it breaks a theme at that theme's critical point.
 */
export function ThresholdPanel({ ctx }: { ctx: GraphToolContext }) {
  const [share, setShare] = useState<"0.3" | "0.5" | "0.7">("0.5");
  const [weighted, setWeighted] = useState(false);
  const [p, setP] = useState(1);
  const [playing, setPlaying] = useState(false);
  const [haloBy, setHaloBy] = useState<"hinge" | "influence">("hinge");
  const [busy, setBusy] = useState(false);
  const key = `${share}|${weighted}`;
  const r = useCached<ThresholdResult>("threshold", ctx.model, key);
  const inf = useCached<Influence>("influence", ctx.model, key);
  const runInfluence = async () => {
    if (!r) return;
    setBusy(true);
    const value = await influence(ctx.model, r, { share: Number(share), weighted });
    useDirectionsCache.getState().put("influence", { model: ctx.model, key, value });
    setBusy(false);
    setHaloBy("influence");
  };

  useEffect(() => {
    if (r) return;
    const t = window.setTimeout(
      () => useDirectionsCache.getState().put("threshold", { model: ctx.model, key, value: thresholds(ctx.model, { share: Number(share), weighted }) }),
      0,
    );
    return () => window.clearTimeout(t);
  }, [r, ctx.model, key, share, weighted]);

  // the slider replays draw 0 on the canvas: links above p fade out; halos mark hinges or influence
  useEffect(() => {
    if (!r) return;
    const halo = new Map<string, number>();
    if (haloBy === "influence" && inf) {
      const max = Math.max(...inf.total.values(), 0.01);
      for (const [id, v] of inf.total) if (v >= 0.25) halo.set(id, Math.min(1, v / max + 0.2));
    } else for (const pt of r.pairs) if (pt.a === pt.b && pt.hinge && pt.p50 <= p) halo.set(pt.hinge, 0.4 + 0.6 * pt.hingeShare);
    useDecor.getState().paint(OWNER, {
      halo,
      linkFade: p >= 1 ? null : (a, b) => {
        const c = r.linkCrit.get(linkKey(a, b));
        return c === undefined ? 0.15 : c <= p ? 1 : 0.04;
      },
    });
  }, [r, p, haloBy, inf]);
  useDecorLifetime(() => useDecor.getState().clear(OWNER));

  // play: sweep p from 0 to 1 in ~8 s
  const raf = useRef(0);
  const pRef = useRef(p);
  pRef.current = p;
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    let v = pRef.current >= 1 ? 0 : pRef.current;
    const step = (now: number) => {
      v = Math.min(1, v + (now - last) / 8000);
      last = now;
      setP(v);
      if (v >= 1) setPlaying(false);
      else raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf.current);
  }, [playing]);

  if (!r) return <p className="text-xs text-muted-foreground">Running 120 percolation draws…</p>;
  const own = r.pairs.filter((x) => x.a === x.b).sort((x, y) => x.p50 - y.p50);
  const cohesion = new Map(own.map((x) => [x.a, x]));
  const excess = (x: PairThreshold) => x.p50 - Math.max(cohesion.get(x.a)?.p50 ?? 0, cohesion.get(x.b)?.p50 ?? 0);
  const hard = r.pairs
    .filter((x) => x.a !== x.b && excess(x) > 0.015)
    .sort((x, y) => excess(y) - excess(x))
    .slice(0, 5);
  const giantAt = r.giant[Math.round(p * 50)]?.share ?? 0;
  const label = (id: string) => ctx.byId.get(id)?.label ?? id;

  return (
    <div className="flex flex-col gap-4 text-xs">
      <Story>
        Keep each link with probability p. At what p does a theme hold together (half its pages in one piece), and does it happen suddenly or bit by bit? A theme
        that needs a high p rests on few links; its hinge is the page that most often tips it over.
      </Story>
      <div className="flex flex-col gap-2">
        <div className="flex items-end gap-2">
          <div className="grow">
            <RangeField label={`Links kept: p = ${num(p)} · largest piece ${pct(giantAt)} of pages`} value={p} min={0} max={1} step={0.01} onChange={setP} />
          </div>
          <Button size="icon" variant="secondary" className="size-8" aria-label={playing ? "Pause" : "Play the sweep"} onClick={() => setPlaying((v) => !v)}>
            {playing ? <Pause aria-hidden /> : <Play aria-hidden />}
          </Button>
        </div>
        <SelectField
          label="Holds together when one piece has"
          value={share}
          options={[
            { id: "0.3", label: "30% of the theme's pages" },
            { id: "0.5", label: "half of the theme's pages" },
            { id: "0.7", label: "70% of the theme's pages" },
          ]}
          onChange={setShare}
        />
        <CheckField label="Links backed by more shared sources survive more often" checked={weighted} onChange={setWeighted} />
      </div>

      <Section title="When each theme holds together" hint="Share of 120 draws in which the theme is cohesive at p">
        <MiniChart
          xLabel="p (links kept)"
          yLabel="share of draws"
          marker={p}
          series={own.map((x) => ({ id: x.a, label: shortTheme(x.a), color: areaColor(x.a), points: GRID.map((g) => ({ x: g, y: heldAt(x, g) })) }))}
        />
        <table className="w-full">
          <thead className="text-muted-foreground">
            <tr>
              <th className="text-left font-normal">Theme</th>
              <th className="text-right font-normal" title="p at which it holds in half the draws">
                p50
              </th>
              <th className="text-right font-normal" title="p90 − p10: narrow = sharp transition">
                width
              </th>
              <th className="text-right font-normal" title="the page at the tipping link in most draws, and how often">
                hinge
              </th>
            </tr>
          </thead>
          <tbody>
            {own.map((x) => (
              <tr key={x.a} className={x.p50 <= p ? "" : "text-muted-foreground"}>
                <td>
                  <ThemeChip theme={x.a} />
                </td>
                <td className="text-right tabular-nums">{num(x.p50)}</td>
                <td className="text-right tabular-nums">{num(x.width)}</td>
                <td className="pl-2 text-right">
                  {x.hinge && (
                    <button type="button" className="block max-w-28 truncate hover:underline" title={`${x.hinge}: at the tipping link in ${pct(x.hingeShare)} of draws`} onClick={() => ctx.focus(x.hinge as string)}>
                      {label(x.hinge)} {pct(x.hingeShare)}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section title="Pairs that need more than their parts" hint="p50 of the pair minus the larger of the two themes' own p50">
        {hard.length ? (
          <ul className="flex flex-col gap-0.5">
            {hard.map((x) => (
              <li key={`${x.a}|${x.b}`} className="flex justify-between gap-2">
                <button type="button" className="truncate text-left hover:underline" onClick={() => x.hinge && ctx.focus(x.hinge)} title="Show the hinge page">
                  {shortTheme(x.a)} × {shortTheme(x.b)}
                </button>
                <span className="shrink-0 tabular-nums text-muted-foreground">+{num(excess(x))}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-muted-foreground">Once two themes each hold together they are already joined: integration is limited by the weakest theme, not by missing bridges.</p>
        )}
      </Section>

      <Section title="Pivotal pages (influence)" hint="Pr[the page is pivotal for a theme at its p50], summed over themes (KKL total influence)">
        <p className="text-muted-foreground">Which single page, removed, most often breaks a theme apart? Those are the pages to strengthen first.</p>
        {inf ? (
          <ul className="flex flex-col gap-0.5">
            {[...inf.total]
              .sort((a, b) => b[1] - a[1])
              .slice(0, 8)
              .map(([id, v]) => {
                const of = [...inf.perTheme].filter(([, l]) => l.some((x) => x.id === id && x.inf >= 0.25)).map(([t]) => shortTheme(t));
                return (
                  <li key={id} className="flex justify-between gap-2">
                    <button type="button" className="truncate text-left hover:underline" onClick={() => ctx.focus(id)} title={of.length ? `pivotal for ${of.join(", ")}` : id}>
                      {label(id)}
                    </button>
                    <span className="shrink-0 tabular-nums text-muted-foreground">{num(v)}</span>
                  </li>
                );
              })}
          </ul>
        ) : (
          <Button size="sm" variant="secondary" className="self-start" onClick={runInfluence} disabled={busy}>
            {busy ? "Measuring…" : "Measure influence"}
          </Button>
        )}
        <SelectField
          label="Halos show"
          value={haloBy}
          options={[
            { id: "hinge", label: "Hinge of each theme that holds at p" },
            { id: "influence", label: "Pivotal pages (influence ≥ 0.25)" },
          ]}
          onChange={setHaloBy}
        />
      </Section>

      <Section title="The largest piece">
        <MiniChart xLabel="p (links kept)" yLabel="share of pages" marker={p} height={80} series={[{ id: "g", label: "largest piece", color: "var(--primary)", points: r.giant.map((g) => ({ x: g.p, y: g.share })) }]} />
      </Section>
    </div>
  );
}
