import { ErrorState, Loading } from "@/components/states";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { HealthCharts } from "./HealthCharts";
import type { HealthLike } from "./model";

/** The groups and labels of the old Health page (core/health.py), in one place. */
const GROUPS: { title: string; keys: [string, string][] }[] = [
  { title: "Integrity", keys: [["errors", "Lint errors"], ["warnings", "Lint warnings"], ["hooks", "Guard hooks"]] },
  { title: "Knowledge", keys: [["broken", "Broken links"], ["orphans", "Orphans"], ["queued", "Queued raw"], ["partial_books", "Partial books"], ["to_read_stubs", "To-read stubs"], ["persons_unverified", "Unverified persons"]] },
  { title: "Coherence", keys: [["coherence_internal", "Internal"], ["coherence_external", "External"], ["coherence_cosmetic", "Cosmetic"], ["coherence_open", "Open"]] },
  { title: "Size", keys: [["wiki_tokens", "Wiki tokens"], ["raw_tokens", "Raw tokens"], ["index_savings_pct", "Index savings %"], ["queued_mb", "Queued MB"]] },
  { title: "Speed", keys: [["lint_ms", "Lint ms"], ["sha1_ms", "Hashing ms"], ["wiki_ms", "Wiki ms"], ["links_ms", "Links ms"]] },
];

/** What each number means: the "?" help of the old Health page (core/health.py METRICS), shown as a tooltip on the label. */
const HELP: Record<string, string> = {
  errors: "Schema violations that must be zero before commit.",
  warnings: "Non-blocking issues (broken links, inbox files) worth fixing soon.",
  hooks: "Whether Cursor and Claude guard hooks point at the write guard (kb_distillery.git.guard).",
  broken: "Links in wiki pages that resolve to no existing slug.",
  orphans: "Wiki pages no other page links to (excluding MOCs and meta slugs).",
  queued: "Raw files in corpus.tsv marked queued — not yet digested.",
  coherence_internal: "Open semantic lint hits (bad ingestion) — fix required.",
  coherence_external: "Open paper-vs-paper tensions — note in Connections.",
  coherence_cosmetic: "Open graph-hygiene hits (asymmetric MOC links, near-duplicates).",
  coherence_open: "Total open semantic coherence warnings across all kinds.",
  lint_ms: "Wall-clock time for the last full health collection run.",
  sha1_ms: "Time spent hashing raw files during manifest reconcile.",
  wiki_ms: "Time spent reading and parsing all wiki frontmatter.",
  links_ms: "Time spent scanning links across all pages.",
  raw_tokens: "Estimated tokens across all of raw/ if fully read (~bytes÷4 per file).",
  wiki_tokens: "Estimated tokens in all wiki page bodies (~chars÷4).",
  index_savings_pct: "Percent of wiki tokens you skip by reading wiki/index.md first instead of every page.",
  queued_mb: "Megabytes of queued raw PDFs — proxy for future ingest/extract cost.",
};

const fmt = (v: unknown) => (typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 1 })) : String(v ?? "—"));
const TONE: Record<string, string> = { ok: "text-ok", warn: "text-warn", bad: "text-bad", error: "text-bad" };

/** Vault health from the lint snapshot: grouped numbers, each coloured by the status lint gave it. */
export function HealthView({ health, error, onRetry }: { health?: HealthLike & { orphan_slugs?: string[] }; error?: unknown; onRetry: () => void }) {
  if (error) return <ErrorState title="Could not load health" error={error} onRetry={onRetry} />;
  if (!health) return <Loading label="Running lint for health" rows={4} />;
  const v = health.values ?? {};
  const st = health.statuses ?? {};
  return (
    <div className="flex flex-col gap-4">
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
                    <dt className="text-muted-foreground" title={HELP[k]} tabIndex={HELP[k] ? 0 : undefined}>{label}</dt>
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
      <HealthCharts health={health} />
      {!!health.compression_pct && (
        <p className="text-sm text-muted-foreground">
          Wiki is ~{health.compression_pct}% of estimated raw tokens ({health.wiki_pages} pages · {health.raw_files} raw files)
          {health.generated_at ? ` · updated ${health.generated_at}` : ""}
        </p>
      )}
    </div>
  );
}
