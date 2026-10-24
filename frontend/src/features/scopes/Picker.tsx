import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useDataSource } from "@/api";
import { Empty } from "@/components/states";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useKb } from "@/lib/store";
import { FORMATS, corpusToRow, formatOf, isDigested, matchPages, matchRaw, nameOf, newRows } from "./logic";
import type { ScopeRow } from "@/api/types";

interface Props {
  have: ReadonlySet<string>;
  onAdd: (rows: ScopeRow[], label: string) => void;
}

/** Add files to the scope: search pages (sources, concepts) and raw files; a page resolves to the raw files it cites. */
export function Picker({ have, onAdd }: Props) {
  const ds = useDataSource();
  const selection = useKb((s) => s.selection);
  const [q, setQ] = useState("");
  const [preview, setPreview] = useState<{ label: string; nodes: string[] } | null>(null);
  const searching = q.trim().length > 0;

  const pages = useQuery({ queryKey: ["pages-index"], queryFn: () => ds.listPages(), enabled: searching, staleTime: 60_000 });
  const corpus = useQuery({
    queryKey: ["corpus-all"],
    enabled: searching,
    staleTime: 60_000,
    queryFn: async () => {
      const tables = await Promise.all(FORMATS.map((f) => ds.getCorpus(f).then((t) => ({ f, t })).catch(() => null)));
      return tables.flatMap((x) => (x ? x.t.rows.map((r) => corpusToRow(r, x.f)) : []));
    },
  });
  const resolved = useQuery({
    queryKey: ["scope-resolve", preview?.nodes],
    queryFn: () => ds.resolveScope({ nodes: preview?.nodes ?? [] }),
    enabled: !!preview,
  });

  const pageHits = useMemo(() => matchPages(pages.data?.pages ?? [], q), [pages.data, q]);
  const rawHits = useMemo(() => matchRaw(corpus.data ?? [], have, q), [corpus.data, have, q]);
  const fresh = resolved.data ? newRows([...have].map((p) => ({ path: p }) as ScopeRow), resolved.data.rows) : [];
  const selected = [...selection];

  return (
    <section aria-label="Add files" className="flex flex-col gap-2 rounded-lg border p-3">
      <h3 className="text-sm font-semibold">Add files</h3>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="Search pages and raw files"
          placeholder="Search pages, concepts or raw files…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="min-w-0 flex-1 basis-56"
        />
        {selected.length > 0 && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPreview({ label: `${selected.length} selected on the graph`, nodes: selected })}
          >
            Resolve graph selection ({selected.length})
          </Button>
        )}
      </div>

      {preview && (
        <div className="flex flex-col gap-2 rounded-md bg-secondary p-3 text-sm" role="region" aria-label="Resolve preview">
          <p className="font-medium">{preview.label}</p>
          {resolved.isLoading && <p className="text-muted-foreground">Resolving…</p>}
          {resolved.isError && <p className="text-bad">Could not resolve: {(resolved.error as Error).message}</p>}
          {resolved.data && (
            <>
              <p className="text-muted-foreground">
                {resolved.data.rows.length} raw file{resolved.data.rows.length === 1 ? "" : "s"}, {fresh.length} not in the scope yet
              </p>
              <ul className="max-h-32 overflow-y-auto font-mono text-xs">
                {fresh.slice(0, 40).map((r) => (
                  <li key={r.path} className="truncate" title={r.path}>
                    {formatOf(r.path)} / {nameOf(r.path)}
                  </li>
                ))}
              </ul>
            </>
          )}
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={!fresh.length}
              onClick={() => {
                onAdd(fresh, preview.label);
                setPreview(null);
              }}
            >
              Add {fresh.length} file{fresh.length === 1 ? "" : "s"}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setPreview(null)}>
              Close
            </Button>
          </div>
        </div>
      )}

      {searching && (
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <h4 className="mb-1 text-xs font-medium uppercase text-muted-foreground">Pages</h4>
            {pages.isLoading ? (
              <Empty>Searching…</Empty>
            ) : pageHits.length ? (
              <ul className="flex flex-col gap-1">
                {pageHits.map((c) => (
                  <li key={c.id} className="flex items-center gap-2 text-sm">
                    <Badge variant="outline">{c.type}</Badge>
                    <span className="min-w-0 flex-1 truncate" title={c.id}>
                      {c.title || c.id}
                    </span>
                    <Button size="sm" variant="secondary" onClick={() => setPreview({ label: c.title || c.id, nodes: [c.id] })}>
                      Resolve
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No matching pages.</Empty>
            )}
          </div>
          <div>
            <h4 className="mb-1 text-xs font-medium uppercase text-muted-foreground">Raw files</h4>
            {corpus.isLoading ? (
              <Empty>Searching…</Empty>
            ) : rawHits.length ? (
              <ul className="flex flex-col gap-1">
                {rawHits.map((r) => (
                  <li key={r.path} className="flex items-center gap-2 text-sm">
                    <Badge variant={isDigested(r) ? "ok" : "warn"}>{r.disposition}</Badge>
                    <span className="min-w-0 flex-1 truncate" title={r.path}>
                      {formatOf(r.path)} / {nameOf(r.path)}
                    </span>
                    <Button size="sm" variant="secondary" aria-label={`Add ${nameOf(r.path)}`} onClick={() => onAdd([r], nameOf(r.path))}>
                      + add
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <Empty>No matching files outside this scope.</Empty>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
