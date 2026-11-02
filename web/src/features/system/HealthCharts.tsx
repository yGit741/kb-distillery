import type { ReactNode } from "react";
import { Empty } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { HealthLike } from "./model";

/** The four charts of the old Health page, as bar lists: same series, status colours from the theme tokens. */

interface Bar {
  label: string;
  value: number;
  /** A Tailwind background token class: `bg-ok`, `bg-warn`, `bg-bad`, `bg-primary` or a neutral. */
  tone: string;
}

const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : 0);
const rec = (v: unknown): Record<string, unknown> => (v && typeof v === "object" ? (v as Record<string, unknown>) : {});

export const LINT_CATEGORIES = ["coherence", "wiki", "raw", "inbox", "corpus", "root", "other"] as const;

export function inDegreeBars(g: HealthLike["graphs"]): Bar[] {
  const d = rec(g?.in_degree);
  return [
    { label: "0 inbound", value: num(d["0"]), tone: "bg-bad" },
    { label: "1 inbound", value: num(d["1"]), tone: "bg-warn" },
    { label: "2+ inbound", value: num(d["2+"]), tone: "bg-ok" },
  ];
}

export function phaseBars(g: HealthLike["graphs"]): Bar[] {
  const d = rec(g?.lint_phases_ms);
  return [
    { label: "SHA1", value: num(d.sha1), tone: "bg-primary" },
    { label: "Wiki", value: num(d.wiki), tone: "bg-primary" },
    { label: "Links", value: num(d.links), tone: "bg-primary" },
  ];
}

export function coherenceBars(g: HealthLike["graphs"]): Bar[] {
  const d = rec(g?.coherence_by_kind);
  return [
    { label: "Internal", value: num(d.internal), tone: "bg-bad" },
    { label: "External", value: num(d.external), tone: "bg-warn" },
    { label: "Cosmetic", value: num(d.cosmetic), tone: "bg-muted-foreground/50" },
  ];
}

/** Errors and warnings per category; categories with neither are left out, as on the old page. */
export function lintIssueBars(g: HealthLike["graphs"]): Bar[] {
  const by = rec(g?.lint_by_category);
  const errors = rec(by.errors);
  const warnings = rec(by.warnings);
  return LINT_CATEGORIES.filter((c) => num(errors[c]) > 0 || num(warnings[c]) > 0).flatMap((c) => [
    { label: `${c} · errors`, value: num(errors[c]), tone: "bg-bad" },
    { label: `${c} · warnings`, value: num(warnings[c]), tone: "bg-warn" },
  ]);
}

function Bars({ bars, unit, name }: { bars: Bar[]; unit?: string; name: string }) {
  const max = Math.max(...bars.map((b) => b.value), 0);
  return (
    <ul className="flex flex-col gap-1.5" aria-label={name}>
      {bars.map((b) => (
        <li key={b.label} className="grid grid-cols-[7.5rem_1fr_auto] items-center gap-2 text-sm">
          <span className="truncate text-muted-foreground" title={b.label}>{b.label}</span>
          <span className="h-3 overflow-hidden rounded bg-muted" aria-hidden>
            <span className={cn("block h-full rounded", b.tone)} style={{ width: max > 0 ? `${(b.value / max) * 100}%` : 0 }} />
          </span>
          <span className="text-right tabular-nums">
            {Number.isInteger(b.value) ? b.value : b.value.toFixed(1)}
            {unit}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Chart({ title, help, children }: { title: string; help: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{help}</CardDescription>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function HealthCharts({ health }: { health: HealthLike }) {
  const g = health.graphs;
  if (!g) return null;
  const issues = lintIssueBars(g);
  return (
    <div className="grid gap-4 sm:grid-cols-2" data-testid="health-charts">
      <Chart title="Inbound links" help="Pages by how many other wiki pages link to them (0 = orphan).">
        <Bars name="Inbound links" bars={inDegreeBars(g)} />
      </Chart>
      <Chart title="Lint phases" help="Where time goes during a full health collection run.">
        <Bars name="Lint phases" bars={phaseBars(g)} unit=" ms" />
      </Chart>
      <Chart title="Coherence by kind" help="Open semantic coherence warnings grouped by disposition kind.">
        <Bars name="Coherence by kind" bars={coherenceBars(g)} />
      </Chart>
      <Chart title="Lint issues" help="Errors and warnings by source category (schema, links, coherence, …).">
        {issues.length ? <Bars name="Lint issues" bars={issues} /> : <Empty>No lint issues.</Empty>}
      </Chart>
    </div>
  );
}
