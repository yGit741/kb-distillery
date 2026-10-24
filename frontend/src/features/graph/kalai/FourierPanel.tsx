import { useEffect, useState } from "react";
import { CheckField, SelectField } from "../controls";
import type { GraphToolContext } from "../tools";
import { notablePairs, spectrum, type AttentionTarget, type PairStat, type Spectrum } from "./fourier";
import { num, pct, Section, shortTheme, Story, ThemeChip, useCached, useKalaiCache } from "./ui";

/** Diverging cell colour: primary for "together more than chance", destructive for "less", neutral at 0. */
function cellColor(coef: number, max: number): string {
  const t = Math.min(1, Math.abs(coef) / (max || 1));
  const pole = coef >= 0 ? "var(--primary)" : "var(--destructive)";
  return `color-mix(in oklab, ${pole} ${Math.round(8 + 80 * t)}%, var(--muted))`;
}

function Heatmap({ s, onPick }: { s: Spectrum; onPick: (p: PairStat) => void }) {
  const max = Math.max(...s.pairs.map((p) => Math.abs(p.coef)));
  const at = new Map(s.pairs.map((p) => [`${p.a}|${p.b}`, p]));
  const pair = (i: number, j: number) => at.get(`${s.themes[Math.min(i, j)]}|${s.themes[Math.max(i, j)]}`);
  return (
    <div className="overflow-x-auto">
      <table className="border-separate border-spacing-[2px] text-[10px]">
        <tbody>
          {s.themes.map((row, i) => (
            <tr key={row}>
              <th scope="row" className="pr-1 text-right font-normal text-muted-foreground" title={row}>
                {shortTheme(row)}
              </th>
              {s.themes.map((col, j) => {
                if (j >= i) return <td key={col} />;
                const p = pair(i, j);
                if (!p) return <td key={col} />;
                return (
                  <td key={col} className="p-0">
                    <button
                      type="button"
                      aria-label={`${p.a} × ${p.b}`}
                      title={`${p.a} × ${p.b}\n${p.both} pages together, ${num(p.expected, 1)} expected by chance\ncoefficient ${num(p.coef)}`}
                      onClick={() => onPick(p)}
                      className="block size-5 rounded-sm outline-offset-1 hover:outline hover:outline-1 hover:outline-foreground"
                      style={{ background: cellColor(p.coef, max) }}
                    />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
        <span className="inline-block size-2.5 rounded-sm" style={{ background: cellColor(-max, max) }} /> less than chance
        <span className="inline-block size-2.5 rounded-sm" style={{ background: cellColor(0, max) }} /> as chance
        <span className="inline-block size-2.5 rounded-sm" style={{ background: cellColor(max, max) }} /> more
      </p>
    </div>
  );
}

function PairRow({ p, onPick }: { p: PairStat; onPick: (p: PairStat) => void }) {
  return (
    <li className="flex items-center justify-between gap-2">
      <button type="button" className="truncate text-left hover:underline" onClick={() => onPick(p)} title={`${p.a} × ${p.b}`}>
        {shortTheme(p.a)} × {shortTheme(p.b)}
      </button>
      <span className="shrink-0 tabular-nums text-muted-foreground">
        {p.both} vs {num(p.expected, 1)}
      </span>
    </li>
  );
}

/**
 * The theme spectrum (experiment "fourier"): pair structure as a heatmap, the gaps between big themes, the
 * share of structure in pairs vs triples against a shuffled vault, and what predicts deep reading.
 */
export function FourierPanel({ ctx }: { ctx: GraphToolContext }) {
  const [infer, setInfer] = useState(false);
  const [target, setTarget] = useState<AttentionTarget>("deep");
  const key = `${infer}|${target}`;
  const s = useCached<Spectrum>("fourier", ctx.model, key);
  useEffect(() => {
    if (s) return;
    const t = window.setTimeout(() => useKalaiCache.getState().put("fourier", { model: ctx.model, key, value: spectrum(ctx.model, { infer, target }) }), 0);
    return () => window.clearTimeout(t);
  }, [s, ctx.model, key, infer, target]);

  if (!s) return <p className="text-xs text-muted-foreground">Computing the spectrum…</p>;
  const members = (t: string) => s.members.get(t) ?? [];
  const pick = (p: PairStat) => {
    const a = new Set(members(p.a));
    const both = members(p.b).filter((id) => a.has(id));
    ctx.select(both.length ? both : [...a, ...members(p.b)]);
  };
  const { over, gaps } = notablePairs(s);
  const [l2, l3] = s.levels;
  const r2 = l2 && l2.null ? l2.observed / l2.null : 0;
  const r3 = l3 && l3.null ? l3.observed / l3.null : 0;
  const singles = s.attention.filter((a) => a.set.length === 1).slice(0, 4);
  const duos = s.attention.filter((a) => a.set.length === 2).slice(0, 3);

  return (
    <div className="flex flex-col gap-4 text-xs">
      <Story>
        Each page is a point in {"{0,1}"}
        <sup>{s.themes.length}</sup> (one bit per theme). The spectrum shows how my themes combine beyond how common each one is. Click a cell or a row to light
        those pages.
      </Story>
      <div className="flex flex-col gap-2">
        <CheckField label="Infer themes for untagged pages from their neighbours" checked={infer} onChange={setInfer} />
        <p className="text-muted-foreground">
          {s.n} themed pages{s.inferred ? ` (${s.inferred} inferred)` : ""} · {s.untagged} without a theme
        </p>
      </div>

      <Section title="Pairs, triples or neither?" hint="Level-k energy of the p-biased spectrum against a shuffled vault with the same theme frequencies">
        <ul className="flex flex-col gap-0.5">
          <li className="flex justify-between">
            <span>Pair structure</span>
            <span className="tabular-nums">×{num(r2, 1)} chance</span>
          </li>
          <li className="flex justify-between">
            <span>Triple structure</span>
            <span className="tabular-nums">×{num(r3, 1)} chance</span>
          </li>
        </ul>
        <p className="text-muted-foreground">
          {r2 > 2 * r3 ? "Themes combine two at a time: three-way topics are rare, so a thesis at a triple intersection would be new ground." : "Higher-order combinations matter as much as pairs."}
        </p>
      </Section>

      <Section title="Which themes go together" hint="Level-2 coefficient = correlation of the two theme bits">
        <Heatmap s={s} onPick={pick} />
      </Section>

      <Section title="Treated together">
        <ul className="flex flex-col gap-0.5">
          {over.map((p) => (
            <PairRow key={`${p.a}|${p.b}`} p={p} onPick={pick} />
          ))}
        </ul>
      </Section>
      <Section title="Gaps: big themes that rarely meet" hint="Pages carrying both themes vs the number expected if they were independent">
        <ul className="flex flex-col gap-0.5">
          {gaps.map((p) => (
            <PairRow key={`${p.a}|${p.b}`} p={p} onPick={pick} />
          ))}
        </ul>
        <p className="text-muted-foreground">A gap lights both themes: two separate regions on the graph are a bridge nobody has built yet.</p>
      </Section>

      <Section title="What predicts my attention" hint="Level-1 and level-2 coefficients of the attention signal f = ±1">
        <SelectField
          label="Attention signal"
          value={target}
          options={[
            { id: "deep", label: "Read in depth (full or deep digest)" },
            { id: "digested", label: "Digested at all (easy or more)" },
          ]}
          onChange={setTarget}
        />
        <p className="text-muted-foreground">Baseline: {pct(s.attentionRate)} of themed pages.</p>
        <ul className="flex flex-col gap-0.5">
          {singles.map((a) => (
            <li key={a.set.join("+")} className="flex items-center justify-between gap-2">
              <ThemeChip theme={a.set[0] as string} onClick={() => ctx.select(members(a.set[0] as string))} />
              <span className="tabular-nums" title={`${a.support} pages, coefficient ${num(a.coef)}`}>
                {a.coef > 0 ? "▲" : "▼"} {pct(a.rate)} of {a.support}
              </span>
            </li>
          ))}
        </ul>
        {duos.length > 0 && (
          <>
            <p className="text-muted-foreground">Pairs that matter beyond their parts:</p>
            <ul className="flex flex-col gap-0.5">
              {duos.map((a) => (
                <li key={a.set.join("+")} className="flex items-center justify-between gap-2">
                  <span className="truncate">{a.set.map(shortTheme).join(" × ")}</span>
                  <span className="tabular-nums" title={`interaction coefficient ${num(a.coef)}`}>
                    {a.coef > 0 ? "▲" : "▼"} {pct(a.rate)} of {a.support}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Section>
    </div>
  );
}
