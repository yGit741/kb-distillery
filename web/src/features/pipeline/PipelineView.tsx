import { useEffect, useMemo, useState, type ReactNode } from "react";
import { DEPTHS, type Depth } from "@/api/model";
import { DEPTH_COLORS } from "@/theme/palette";
import type { PipelineSearch } from "@/routes/search";
import { Empty, ErrorState, Loading } from "@/components/states";
import { AddSources } from "@/components/AddSources";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApiQuery } from "@/lib/useApiQuery";
import {
  countUnits, DEPTH_TIP, filterUnits, FORMAT_ORDER, GROUPS, groupByMonth, groupUnits, parseSnapshot, sortUnits,
  STATUS_FILTERS, STATUS_LABEL, STATUS_TIP, VIEWS, type Group, type SnapshotData, type StatusFilter, type Unit, type View,
} from "./items";
import { Dot, statusColor } from "./parts";
import { PreviewDialog } from "./Preview";
import { BoardView, ListView, TimelineView } from "./Views";

export type SearchPatch = { [K in keyof PipelineSearch]?: PipelineSearch[K] | undefined };

const oneOf = <T extends string>(v: string | undefined, allowed: readonly T[], d: T): T =>
  v && (allowed as readonly string[]).includes(v) ? (v as T) : d;

function Seg({ label, count, active, tip, color, onClick }: { label: string; count: number; active: boolean; tip: string; color?: string | null; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      title={tip}
      onClick={onClick}
      className={`flex min-w-[5.5rem] flex-1 flex-col items-start rounded-md border px-3 py-2 text-left text-xs transition-colors hover:bg-accent ${active ? "border-primary bg-accent-soft" : ""}`}
    >
      <span className="text-lg font-semibold tabular-nums leading-none">{count}</span>
      <span className="mt-1 inline-flex items-center gap-1.5 text-muted-foreground">
        {color !== null && <Dot color={color} />}
        {label}
      </span>
    </button>
  );
}

function Step({ n, title, hint, children }: { n: number; title: string; hint: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border bg-card p-3" aria-label={title}>
      <h2 className="text-sm font-semibold">
        <span className="mr-1.5 text-muted-foreground">{n}</span>{title}
      </h2>
      <p className="mb-2 text-xs text-muted-foreground">{hint}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </section>
  );
}

const selectCls = "h-9 min-w-0 max-w-full rounded-md border bg-background px-2 text-sm";

function Toolbar({ data, search, onSearch, shown }: { data: SnapshotData; search: PipelineSearch; onSearch: (p: SearchPatch) => void; shown: number }) {
  const [q, setQ] = useState(search.q ?? "");
  useEffect(() => setQ(search.q ?? ""), [search.q]);
  useEffect(() => {
    if (q === (search.q ?? "")) return;
    const t = setTimeout(() => onSearch({ q: q || undefined }), 200);
    return () => clearTimeout(t);
  }, [q, search.q, onSearch]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      const typing = t instanceof HTMLElement && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
      if (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey) { e.preventDefault(); document.getElementById("pipeline-search")?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const formats = useMemo(() => [...new Set(data.units.map((u) => u.format))].sort((a, b) => (FORMAT_ORDER.indexOf(a) + 1 || 99) - (FORMAT_ORDER.indexOf(b) + 1 || 99)), [data.units]);
  const colls = useMemo(
    () => [...new Set(data.units.flatMap((u) => u.collections))].sort((a, b) => (data.titles[a] ?? a).localeCompare(data.titles[b] ?? b)),
    [data],
  );
  const view = oneOf(search.view, VIEWS, "list");
  const active = !!(search.q || search.format || search.collection || search.status || search.depth || search.backlog);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Input id="pipeline-search" type="search" className="w-full sm:w-64" placeholder="Search ( / )" aria-label="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        <select className={selectCls} aria-label="Format" value={search.format ?? ""} onChange={(e) => onSearch({ format: e.target.value || undefined })}>
          <option value="">All formats</option>
          {formats.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
        <select className={selectCls} aria-label="Collection" value={search.collection ?? ""} onChange={(e) => onSearch({ collection: e.target.value || undefined })}>
          <option value="">All collections</option>
          <option value="@none">(no collection)</option>
          {colls.map((c) => <option key={c} value={c}>{data.titles[c] ?? c}</option>)}
        </select>
        <select className={selectCls} aria-label="Depth" value={search.depth ?? ""} onChange={(e) => onSearch({ depth: e.target.value || undefined })}>
          <option value="">Any depth</option>
          {DEPTHS.map((d) => <option key={d} value={d}>{d}</option>)}
        </select>
        <select className={selectCls} aria-label="Status" value={search.status ?? ""} onChange={(e) => onSearch({ status: e.target.value || undefined })}>
          <option value="">Any status</option>
          {STATUS_FILTERS.map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
        </select>
        <Button variant={search.backlog ? "default" : "secondary"} aria-pressed={!!search.backlog} onClick={() => onSearch({ backlog: search.backlog ? undefined : "queued" })} title="Only files nothing has been done with yet (corpus disposition: queued)">
          Backlog only
        </Button>
        {active && <Button variant="ghost" onClick={() => onSearch({ q: undefined, format: undefined, collection: undefined, status: undefined, depth: undefined, backlog: undefined })}>Clear filters</Button>}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex gap-1" role="group" aria-label="View">
          {VIEWS.map((v) => (
            <Button key={v} size="sm" variant={view === v ? "default" : "secondary"} aria-pressed={view === v} onClick={() => onSearch({ view: v === "list" ? undefined : v })}>
              {v}
            </Button>
          ))}
        </div>
        {view !== "timeline" && (
          <label className="flex items-center gap-2 text-sm text-muted-foreground">
            {view === "board" ? "Columns" : "Group by"}
            <select className={selectCls} value={search.group ?? "none"} onChange={(e) => onSearch({ group: e.target.value === "none" ? undefined : e.target.value })}>
              {GROUPS.map((g) => <option key={g} value={g}>{g === "none" ? (view === "board" ? "status" : "nothing") : g}</option>)}
            </select>
          </label>
        )}
        <span className="ml-auto text-sm text-muted-foreground" aria-live="polite">{shown} item{shown === 1 ? "" : "s"}</span>
      </div>
    </div>
  );
}

function IngestionLog({ data }: { data: SnapshotData }) {
  const name = (p: string) => p.split("/").pop() || p;
  return (
    <details className="rounded-lg border bg-card p-3">
      <summary className="cursor-pointer text-sm font-semibold">
        Ingestion status <span className="font-normal text-muted-foreground">· {data.failures.length} failed · {data.recent.length} recently cataloged</span>
      </summary>
      <p className="mt-2 text-xs text-muted-foreground">Did each file get into the vault properly?</p>
      {data.failures.length > 0 && (
        <div className="mt-2">
          <p className="text-sm font-medium text-bad">Failed to catalog</p>
          <ul className="mt-1 flex flex-col gap-1 text-sm">
            {data.failures.map((f) => <li key={f.path}><span className="break-all">{name(f.path)}</span> <span className="text-muted-foreground">{f.reason}</span></li>)}
          </ul>
        </div>
      )}
      <p className="mt-3 text-sm font-medium">Recently cataloged</p>
      {data.recent.length ? (
        <ul className="mt-1 flex flex-col gap-1 text-sm">
          {data.recent.map((e) => (
            <li key={`${e.ts}${e.path}`} className="flex flex-wrap gap-x-3">
              <span className="text-xs tabular-nums text-muted-foreground" title={`${e.ts} (UTC)`}>{e.ts ? new Date(e.ts).toLocaleString() : ""}</span>
              <span className="break-all">{name(e.dest || e.path)}</span>
              {e.collection && <span className="text-muted-foreground">to {data.titles[e.collection] ?? e.collection}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Nothing logged yet; the log starts with the next catalog run.</p>
      )}
    </details>
  );
}

export function PipelineView({ search, onSearch }: { search: PipelineSearch; onSearch: (p: SearchPatch) => void }) {
  const q = useApiQuery(["pipeline"], (ds) => ds.getPipeline());
  const data = useMemo(() => (q.data ? parseSnapshot(q.data) : null), [q.data]);
  const view: View = oneOf(search.view, VIEWS, "list");
  const group: Group = oneOf(search.group, GROUPS, "none");

  const layout = useMemo(() => {
    if (!data) return null;
    const filtered = filterUnits(data.units, { ...search, backlog: !!search.backlog });
    const sorted = sortUnits(filtered);
    const effective: Group = view === "board" && group === "none" ? "status" : group;
    const groups: [string, Unit[]][] = effective === "none" ? [["", sorted]] : groupUnits(sorted, effective, data.titles);
    const order = (view === "timeline" ? groupByMonth(sorted).flatMap(([, m]) => m) : groups.flatMap(([, m]) => m)).map((u) => u.key);
    return { filtered, groups, order, effective, sorted };
  }, [data, search, view, group]);

  const counts = useMemo(() => (data ? countUnits(data.units) : null), [data]);
  if (q.isPending) return <Loading label="Loading pipeline" rows={4} />;
  if (q.isError || !data || !layout || !counts) return <ErrorState title="Could not load the pipeline" error={q.error} onRetry={() => void q.refetch()} />;

  const toggleStatus = (s: StatusFilter) => onSearch({ status: search.status === s ? undefined : s });
  const toggleDepth = (d: Depth) => onSearch({ depth: search.depth === d ? undefined : d });
  const statusSeg = (s: StatusFilter, count: number) => (
    <Seg key={s} label={STATUS_LABEL[s]} count={count} active={search.status === s} tip={STATUS_TIP[s]} color={s === "cataloged" ? null : statusColor(s)} onClick={() => toggleStatus(s)} />
  );
  const idx = search.item ? layout.order.indexOf(search.item) : -1;
  const open = search.item ? data.units.find((u) => u.key === search.item) ?? null : null;
  const step = (d: -1 | 1) => {
    const next = layout.order[idx + d];
    if (next) onSearch({ item: next });
  };
  const empty = data.units.length === 0;

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Pipeline</h1>
          <p className="text-sm text-muted-foreground">
            {counts.total} items · {counts.backlog} in the backlog{data.queued.mb ? ` (${data.queued.mb} MB)` : ""} · Add, Catalog, Digest
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => void q.refetch()} disabled={q.isFetching}>{q.isFetching ? "Refreshing…" : "Refresh"}</Button>
      </header>

      <div className="grid gap-3 md:grid-cols-3">
        <Step n={1} title="Add" hint="Dropped into raw/inbox/, waiting to be filed.">
          {statusSeg("inbox", counts.status.inbox)}
          {statusSeg("failed", counts.status.failed)}
        </Step>
        <Step n={2} title="Catalog" hint="Filed in a format folder with a record.">
          {statusSeg("uncataloged", counts.status.uncataloged)}
          {statusSeg("cataloged", counts.cataloged)}
        </Step>
        <Step n={3} title="Digest" hint="Read into the wiki. Depth is how deeply.">
          {statusSeg("undigested", counts.status.undigested)}
          {statusSeg("partial", counts.status.partial)}
          {DEPTHS.map((d) => (
            <Seg key={d} label={d} count={counts.depth[d]} active={search.depth === d} tip={DEPTH_TIP[d]} color={DEPTH_COLORS[d]} onClick={() => toggleDepth(d)} />
          ))}
          {statusSeg("skipped", counts.status.skipped)}
        </Step>
      </div>

      <section aria-label="Add sources" className="rounded-lg border bg-card p-3">
        <h2 className="mb-2 text-sm font-semibold">Add sources</h2>
        <AddSources />
      </section>

      <Toolbar data={data} search={search} onSearch={onSearch} shown={layout.filtered.length} />

      {empty ? (
        <Empty>The raw layer is empty. Add files to raw/inbox/ and catalog them.</Empty>
      ) : layout.filtered.length === 0 ? (
        <Empty>Nothing matches. Remove a filter above.</Empty>
      ) : view === "board" ? (
        <BoardView groups={layout.groups} group={layout.effective} titles={data.titles} activeKey={search.item} onOpen={(item) => onSearch({ item })} onFilter={onSearch} />
      ) : view === "timeline" ? (
        <TimelineView units={layout.sorted} activeKey={search.item} onOpen={(item) => onSearch({ item })} />
      ) : (
        <ListView groups={layout.groups} group={layout.effective} titles={data.titles} activeKey={search.item} onOpen={(item) => onSearch({ item })} onFilter={onSearch} />
      )}

      <IngestionLog data={data} />

      <PreviewDialog unit={open} titles={data.titles} onClose={() => onSearch({ item: undefined })} onStep={step} hasPrev={idx > 0} hasNext={idx >= 0 && idx < layout.order.length - 1} />
    </div>
  );
}
