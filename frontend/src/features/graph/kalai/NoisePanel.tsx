import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { CheckField, RangeField, SelectField } from "../controls";
import type { GraphToolContext } from "../tools";
import { useDecor } from "../tools/decor";
import { noiseStability, stabilityCurve, type NoiseMode, type NoiseResult } from "./noise";
import { MiniChart, num, pct, Section, Story, useCached, useDecorLifetime, useKalaiCache } from "./ui";

const OWNER = "kalai-noise";
/** below this cluster Jaccard a page gets a halo; at or above STABLE it is in the stable core */
const FRAGILE = 0.6;
const STABLE = 0.8;
const CURVE_EPS = [0, 0.05, 0.1, 0.2, 0.3, 0.5] as const;

type Curve = { eps: number; meanStability: number; meanTopKeep: number }[];

/**
 * Noise stability (experiment "noise"): re-run the clustering and the ranking on a vault with eps of its
 * links or sources dropped, and paint a halo on every page whose company changes. Halos = conclusions that
 * are noise-sensitive.
 */
export function NoisePanel({ ctx }: { ctx: GraphToolContext }) {
  const [eps, setEps] = useState(0.15);
  const [mode, setMode] = useState<NoiseMode>("sources");
  const [halos, setHalos] = useState(true);
  const [progress, setProgress] = useState<string | null>(null);
  const key = `${eps}|${mode}`;
  const r = useCached<NoiseResult>("noise", ctx.model, key);
  const curve = useCached<Curve>("noise-curve", ctx.model, mode);
  const byId = ctx.byId;

  const run = async () => {
    setProgress("0 / 10 runs");
    const value = await noiseStability(ctx.model, { eps, mode, runs: 10, onProgress: (d, t) => setProgress(`${d} / ${t} runs`) });
    useKalaiCache.getState().put("noise", { model: ctx.model, key, value });
    setProgress(null);
  };
  const runCurve = async () => {
    setProgress("decay curve…");
    const value = await stabilityCurve(ctx.model, { eps: CURVE_EPS, mode, runs: 4, onProgress: (d, t) => setProgress(`decay curve ${d} / ${t}`) });
    useKalaiCache.getState().put("noise-curve", { model: ctx.model, key: mode, value });
    setProgress(null);
  };

  useEffect(() => {
    if (!r || !halos) return useDecor.getState().clear(OWNER);
    const halo = new Map<string, number>();
    for (const [id, v] of r.clusterStability) if (v < FRAGILE) halo.set(id, Math.min(1, (FRAGILE - v) / FRAGILE + 0.25));
    useDecor.getState().paint(OWNER, { halo, linkFade: null });
  }, [r, halos]);
  useDecorLifetime(() => useDecor.getState().clear(OWNER));

  const shaky = r
    ? [...r.clusterStability]
        .filter(([id]) => byId.get(id)?.layer === "concept")
        .sort((a, b) => a[1] - b[1])
        .slice(0, 8)
    : [];
  const flips = r ? r.top.filter((id) => (r.topKeep.get(id) ?? 1) < 0.999) : [];
  const stableCore = r ? [...r.clusterStability.values()].filter((v) => v >= STABLE).length : 0;
  const label = (id: string) => byId.get(id)?.label ?? id;

  return (
    <div className="flex flex-col gap-4 text-xs">
      <Story>
        If I had not read {pct(eps)} of my sources (or not written {pct(eps)} of my links), would my map still say the same thing? Pages with a halo change
        their company under that noise: do not build an argument on their cluster.
      </Story>
      <div className="flex flex-col gap-2">
        <SelectField
          label="Noise"
          value={mode}
          options={[
            { id: "sources", label: "Drop sources (papers I might not have read)" },
            { id: "links", label: "Drop links (connections I might not have written)" },
          ]}
          onChange={setMode}
        />
        <RangeField label={`How much: ${pct(eps)}`} value={eps} min={0.05} max={0.5} step={0.05} onChange={setEps} />
        <div className="flex gap-2">
          <Button size="sm" onClick={run} disabled={progress !== null}>
            {r ? "Re-run" : "Run"} 10 trials
          </Button>
          <Button size="sm" variant="secondary" onClick={runCurve} disabled={progress !== null}>
            Decay curve
          </Button>
        </div>
        {progress && <p className="text-muted-foreground">{progress}</p>}
        <CheckField label="Halos on the graph" checked={halos} onChange={setHalos} />
      </div>

      {r && (
        <>
          <Section title="How much survives">
            <ul className="flex flex-col gap-0.5">
              <li className="flex justify-between">
                <span>Clusters (mean Jaccard)</span>
                <span className="tabular-nums">{num(r.meanStability)}</span>
              </li>
              <li className="flex justify-between">
                <span>Top {r.top.length} concepts kept</span>
                <span className="tabular-nums">{pct(r.meanTopKeep)}</span>
              </li>
              <li className="flex justify-between">
                <span>Stable core (≥ {STABLE})</span>
                <span className="tabular-nums">
                  {stableCore} of {r.clusterStability.size} pages
                </span>
              </li>
            </ul>
            <Button size="sm" variant="ghost" className="self-start" onClick={() => ctx.select([...r.clusterStability].filter(([, v]) => v >= STABLE).map(([id]) => id))}>
              Select the stable core
            </Button>
          </Section>
          <Section title="Fragile concepts" hint="Lowest cluster stability among ideas, questions, people">
            <ul className="flex flex-col gap-0.5">
              {shaky.map(([id, v]) => (
                <li key={id} className="flex justify-between gap-2">
                  <button type="button" className="truncate text-left hover:underline" onClick={() => ctx.focus(id)} title={id}>
                    {label(id)}
                  </button>
                  <span className="shrink-0 tabular-nums text-muted-foreground">{num(v)}</span>
                </li>
              ))}
            </ul>
          </Section>
          <Section title="Central, but not for sure" hint="Top concepts by PageRank that drop out of the top in some runs">
            {flips.length ? (
              <ul className="flex flex-col gap-0.5">
                {flips.map((id) => (
                  <li key={id} className="flex justify-between gap-2">
                    <button type="button" className="truncate text-left hover:underline" onClick={() => ctx.focus(id)} title={id}>
                      {label(id)}
                    </button>
                    <span className="shrink-0 tabular-nums text-muted-foreground">kept {pct(r.topKeep.get(id) ?? 0)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted-foreground">Every top concept stays on top: the ranking is noise-stable.</p>
            )}
          </Section>
        </>
      )}
      {curve && (
        <Section title="Decay under growing noise">
          <MiniChart
            xLabel="noise"
            yLabel="what survives"
            marker={eps}
            series={[
              { id: "c", label: "clusters", color: "var(--primary)", points: curve.map((c) => ({ x: c.eps, y: c.meanStability })) },
              { id: "t", label: "top concepts", color: "var(--foreground)", points: curve.map((c) => ({ x: c.eps, y: c.meanTopKeep })) },
            ]}
          />
          <p className="text-muted-foreground">A curve that drops steeply near 0 is noise-sensitive (BKS); a flat one is stable.</p>
        </Section>
      )}
    </div>
  );
}
