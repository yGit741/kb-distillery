import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { areaColor } from "@/theme/palette";
import { CheckField, RangeField, SelectField } from "../controls";
import type { GraphToolContext } from "../tools";
import { useDecor } from "../tools/decor";
import { heldAt, linkKey, thresholds, type PairThreshold, type ThresholdResult } from "./threshold";
import { MiniChart, num, pct, Section, shortTheme, Story, ThemeChip, useCached, useDecorLifetime, useKalaiCache } from "./ui";

const OWNER = "kalai-threshold";
const GRID = Array.from({ length: 51 }, (_, i) => i / 50);

/**
 * Sharp thresholds (experiment "threshold"): the p slider keeps each link with probability p (one fixed
 * draw, so moving it right only ever adds links) and the panel shows, over many draws, at which p each
 * theme holds together and how sharply. The link that tipped a theme over is its bridge.
 */
export function ThresholdPanel({ ctx }: { ctx: GraphToolContext }) {
  const [share, setShare] = useState<"0.3" | "0.5" | "0.7">("0.5");
  const [weighted, setWeighted] = useState(false);
  const [p, setP] = useState(1);
  const [playing, setPlaying] = useState(false);
  const key = `${share}|${weighted}`;
  const r = useCached<ThresholdResult>("threshold", ctx.model, key);

  useEffect(() => {
    if (r) return;
    const t = window.setTimeout(
      () => useKalaiCache.getState().put("threshold", { model: ctx.model, key, value: thresholds(ctx.model, { share: Number(share), weighted }) }),
      0,
    );
    return () => window.clearTimeout(t);
  }, [r, ctx.model, key, share, weighted]);

  // the slider replays draw 0 on the canvas: links above p fade out, bridges get a halo
  useEffect(() => {
    if (!r) return;
    const halo = new Map<string, number>();
    for (const pt of r.pairs) if (pt.a === pt.b && pt.bridge && pt.p50 <= p) for (const id of pt.bridge) halo.set(id, 0.7);
    useDecor.getState().paint(OWNER, {
      halo,
      linkFade: p >= 1 ? null : (a, b) => {
        const c = r.linkCrit.get(linkKey(a, b));
        return c === undefined ? 0.15 : c <= p ? 1 : 0.04;
      },
    });
  }, [r, p]);
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
  const pickBridge = (b: [string, string] | null) => b && ctx.select(b);

  return (
    <div className="flex flex-col gap-4 text-xs">
      <Story>
        Keep each link with probability p. At what p does a theme hold together (half its pages in one piece), and does it happen suddenly or bit by bit? A theme
        that needs a high p rests on few links; its bridge is the link that tipped it over.
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
              <th className="text-right font-normal">bridge</th>
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
                  {x.bridge && (
                    <button type="button" className="block max-w-24 truncate hover:underline" title={`${label(x.bridge[0])} — ${label(x.bridge[1])}`} onClick={() => pickBridge(x.bridge)}>
                      {label(x.bridge[1])}
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
                <button type="button" className="truncate text-left hover:underline" onClick={() => pickBridge(x.bridge)} title="Select the bridge of draw 0">
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

      <Section title="The largest piece">
        <MiniChart xLabel="p (links kept)" yLabel="share of pages" marker={p} height={80} series={[{ id: "g", label: "largest piece", color: "var(--primary)", points: r.giant.map((g) => ({ x: g.p, y: g.share })) }]} />
      </Section>
    </div>
  );
}
