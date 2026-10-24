import { ErrorState, Loading } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { HealthLike } from "./model";

/** The groups and labels of the old Health page (core/health.py), in one place. */
const GROUPS: { title: string; keys: [string, string][] }[] = [
  { title: "Integrity", keys: [["errors", "Lint errors"], ["warnings", "Lint warnings"], ["hooks", "Guard hooks"]] },
  { title: "Knowledge", keys: [["broken", "Broken links"], ["orphans", "Orphans"], ["queued", "Queued raw"], ["partial_books", "Partial books"], ["to_read_stubs", "To-read stubs"], ["persons_unverified", "Unverified persons"]] },
  { title: "Coherence", keys: [["coherence_internal", "Internal"], ["coherence_external", "External"], ["coherence_cosmetic", "Cosmetic"], ["coherence_open", "Open"]] },
  { title: "Size", keys: [["wiki_tokens", "Wiki tokens"], ["raw_tokens", "Raw tokens"], ["index_savings_pct", "Index savings %"], ["queued_mb", "Queued MB"]] },
  { title: "Speed", keys: [["lint_ms", "Lint ms"], ["sha1_ms", "Hashing ms"], ["wiki_ms", "Wiki ms"], ["links_ms", "Links ms"]] },
];

const fmt = (v: unknown) => (typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 1 })) : String(v ?? "—"));
const TONE: Record<string, string> = { ok: "text-ok", warn: "text-warn", bad: "text-bad", error: "text-bad" };

/** Vault health from the lint snapshot: grouped numbers, each coloured by the status lint gave it. */
export function HealthView({ health, error, onRetry }: { health?: HealthLike & { orphan_slugs?: string[] }; error?: unknown; onRetry: () => void }) {
  if (error) return <ErrorState title="Could not load health" error={error} onRetry={onRetry} />;
  if (!health) return <Loading label="Running lint for health" rows={4} />;
  const v = health.values ?? {};
  const st = health.statuses ?? {};
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {GROUPS.map((g) => (
        <Card key={g.title}>
          <CardHeader>
            <CardTitle>{g.title}</CardTitle>
          </CardHeader>
          <CardContent>
            <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
              {g.keys.map(([k, label]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className={cn("text-right tabular-nums", TONE[st[k] ?? ""])}>{fmt(v[k])}</dd>
                </div>
              ))}
            </dl>
          </CardContent>
        </Card>
      ))}
      {!!health.orphan_slugs?.length && (
        <Card>
          <CardHeader>
            <CardTitle>Orphans</CardTitle>
            <CardDescription>Pages nothing links to.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-wrap gap-1.5">
              {health.orphan_slugs.slice(0, 40).map((s) => (
                <li key={s} className="rounded-full border px-2 py-0.5 text-xs">
                  {s}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
