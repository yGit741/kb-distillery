import { useEffect } from "react";
import { Button } from "@/components/ui/button";
import type { GraphToolContext } from "../tools";
import { directions, type Direction, type DirectionPage } from "./directions";
import { spectrum, type Spectrum } from "./fourier";
import { num, Section, shortTheme, Story, ThemeChip, useCached, useDirectionsCache } from "./ui";

const FOOTHOLD: Record<Direction["foothold"], { label: string; hint: string }> = {
  strong: { label: "strong foothold", hint: "some of my questions or ideas already reach every side" },
  thin: { label: "thin foothold", hint: "the notes touch every side, but only lightly" },
  none: { label: "greenfield", hint: "nothing I wrote reaches every side yet: new ground, and a cold start" },
};

function PageList({ title, pages, ctx }: { title: string; pages: readonly DirectionPage[]; ctx: GraphToolContext }) {
  if (!pages.length) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-muted-foreground">{title}</span>
      <ul className="flex flex-col gap-0.5">
        {pages.map((p) => (
          <li key={p.id} className="flex justify-between gap-2">
            <button type="button" className="truncate text-left hover:underline" onClick={() => ctx.focus(p.id)} title={p.id}>
              {ctx.byId.get(p.id)?.title ?? p.id}
            </button>
            <span className="shrink-0 tabular-nums text-muted-foreground" title="reach: closeness to the weakest side">
              {num(p.reach)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Card({ d, ctx }: { d: Direction; ctx: GraphToolContext }) {
  const f = FOOTHOLD[d.foothold];
  const show = () => ctx.select([...d.existing, ...d.questions.map((p) => p.id), ...d.ideas.map((p) => p.id)]);
  return (
    <article className="flex flex-col gap-2 rounded-md border p-2">
      <header className="flex flex-wrap items-center gap-x-1">
        {d.sides.map((s, i) => (
          <span key={s.theme} className="inline-flex items-center">
            {i > 0 && <span className="px-0.5 text-muted-foreground">×</span>}
            <ThemeChip theme={s.theme} />
          </span>
        ))}
      </header>
      <p className="flex flex-wrap gap-x-2 text-muted-foreground">
        <span>{d.kind === "hole" ? "meet only in pairs" : "rarely meet"}</span>
        <span className="tabular-nums">
          {d.existing.length} {d.existing.length === 1 ? "page" : "pages"} vs {num(d.expected, 1)} expected
        </span>
        <span className={d.foothold === "strong" ? "text-primary" : ""} title={f.hint}>
          · {f.label}
        </span>
      </p>
      <p className="text-muted-foreground" title="Sources read in full or deep, of all pages in the theme">
        Read in depth: {d.sides.map((s) => `${shortTheme(s.theme)} ${s.deep}/${s.pages}`).join(" · ")}
      </p>
      <PageList title="Closest open questions" pages={d.questions} ctx={ctx} />
      <PageList title="Closest ideas" pages={d.ideas} ctx={ctx} />
      <Button size="sm" variant="secondary" className="self-start" onClick={show}>
        Show on graph
      </Button>
    </article>
  );
}

/**
 * Research directions (experiment "directions"): the gaps and holes of the theme spectrum as cards to
 * choose a thesis from, each with what already sits there and my nearest questions and ideas.
 */
export function DirectionsPanel({ ctx }: { ctx: GraphToolContext }) {
  const s = useCached<Spectrum>("fourier", ctx.model, "false|deep");
  const list = useCached<Direction[]>("directions", ctx.model, "default");
  useEffect(() => {
    if (list) return;
    const t = window.setTimeout(() => {
      const spec = s ?? spectrum(ctx.model);
      useDirectionsCache.getState().put("directions", { model: ctx.model, key: "default", value: directions(ctx.model, spec) });
    }, 0);
    return () => window.clearTimeout(t);
  }, [list, s, ctx.model]);

  if (!list) return <p className="text-xs text-muted-foreground">Finding directions…</p>;
  const strong = list.filter((d) => d.foothold === "strong").length;
  return (
    <div className="flex flex-col gap-4 text-xs">
      <Story>
        Where could a research focus sit? Each card is an intersection the vault leaves empty: big themes that rarely share a page, or three themes that meet only in
        pairs. A strong foothold means the vault's own questions already reach every side; greenfield means new ground with a cold start.
      </Story>
      <Section title={`${list.length} directions · ${strong} with a strong foothold`}>
        <div className="flex flex-col gap-2">
          {list.map((d) => (
            <Card key={d.id} d={d} ctx={ctx} />
          ))}
        </div>
      </Section>
    </div>
  );
}
