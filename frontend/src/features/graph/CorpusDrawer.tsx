import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ApiError, useDataSource } from "@/api";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useApiQuery } from "@/lib/useApiQuery";
import { pileColor } from "@/theme/palette";
import { activeDraft, UNTITLED, useBasket } from "./basket";
import { CitationView } from "./CitationView";
import {
  canDigest,
  dispositionChips,
  filterRows,
  fromCorpus,
  fromScopeRows,
  isDigestedRow,
  nameOfPath,
  ROW_CAP,
  sortRows,
  toScopeRow,
  type DrawerRow,
  type SortKey,
} from "./corpusRows";
import { useToolHost } from "./hostContext";
import { useLayer, type DrawerView } from "./layerStore";
import { dispositionHead } from "./rawLayer";
import { pageIds } from "./selection";
import type { GraphToolContext } from "./tools";

const COLUMNS: { key: SortKey; label: string; cls?: string }[] = [
  { key: "name", label: "File" },
  { key: "disposition", label: "State" },
  { key: "slug", label: "Page", cls: "hidden sm:table-cell" },
  { key: "year", label: "Year", cls: "hidden md:table-cell" },
];

const TITLES: Record<DrawerView["kind"], string> = { format: "Raw files", selection: "Raw files behind the selection", genealogy: "Citation genealogy" };

/**
 * The bottom drawer: the raw files of one format or behind the selection (filter, sort, preview, scope
 * draft, Pipeline, easy-digest), and a paper's citation genealogy. Opened from the Raw files tool, a pile
 * on the canvas, or the page menu.
 */
export function CorpusDrawer({ ctx }: { ctx: GraphToolContext }) {
  const view = useLayer((s) => s.drawer);
  const close = () => useLayer.getState().openDrawer(null);

  useEffect(() => {
    if (!view) return;
    // capture phase on the window: the screen's own Escape (clear selection) must not also fire
    const key = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      const t = e.target;
      if (t instanceof HTMLElement && t.matches("input, textarea, select")) return;
      e.stopPropagation();
      close();
    };
    window.addEventListener("keydown", key, true);
    return () => window.removeEventListener("keydown", key, true);
  }, [view]);

  if (!view) return null;
  return (
    <section
      aria-label={view.kind === "format" ? `${view.format} files` : TITLES[view.kind]}
      className="pointer-events-auto absolute inset-x-0 bottom-0 z-10 flex h-[min(52%,30rem)] flex-col border-t pr-14 bg-card shadow-[var(--shadow)]"
    >
      {view.kind === "genealogy" ? (
        <>
          <header className="flex items-center justify-between border-b px-3 py-1.5">
            <h2 className="text-sm font-semibold">{TITLES.genealogy}</h2>
            <Button variant="ghost" size="icon" className="size-7" aria-label="Close drawer" onClick={close}>
              <X aria-hidden />
            </Button>
          </header>
          <div className="min-h-0 flex-1">
            <GenealogyBody focus={view.focus} ctx={ctx} />
          </div>
        </>
      ) : (
        <FilesBody view={view} ctx={ctx} onClose={close} />
      )}
    </section>
  );
}

function GenealogyBody({ focus, ctx }: { focus: string; ctx: GraphToolContext }) {
  const isSource = useMemo(() => (id: string) => ctx.byId.get(id)?.layer === "source", [ctx.byId]);
  return (
    <CitationView
      focus={focus}
      isSource={isSource}
      titleOf={(id) => ctx.byId.get(id)?.title || id}
      onPick={(id) => {
        if (ctx.byId.has(id)) {
          ctx.select([id]);
          ctx.focus(id, false);
        }
      }}
    />
  );
}

function FilesBody({ view, ctx, onClose }: { view: Exclude<DrawerView, { kind: "genealogy" }>; ctx: GraphToolContext; onClose: () => void }) {
  const ids = useMemo(() => pageIds(ctx.selection, ctx.byId), [ctx.selection, ctx.byId]);
  const byFormat = view.kind === "format";
  const corpus = useApiQuery(["corpus", byFormat ? view.format : ""], (d) => d.getCorpus(view.kind === "format" ? view.format : ""), { enabled: byFormat });
  const resolved = useApiQuery(["resolve", ...ids], (d) => d.resolveScope({ nodes: ids }), { enabled: !byFormat && ids.length > 0 });
  const q = byFormat ? corpus : resolved;
  const rows = useMemo<DrawerRow[]>(
    () => (byFormat ? (corpus.data ? fromCorpus(corpus.data.rows, view.format) : []) : resolved.data ? fromScopeRows(resolved.data.rows) : []),
    [byFormat, corpus.data, resolved.data, view],
  );
  const [text, setText] = useState("");
  const [chips, setChips] = useState<ReadonlySet<string>>(new Set());
  const [sort, setSort] = useState<{ key: SortKey | null; dir: 1 | -1 }>({ key: null, dir: 1 });
  const [picked, setPicked] = useState<string | null>(view.path ?? null);
  useEffect(() => setPicked(view.path ?? null), [view]);

  const shown = useMemo(() => sortRows(filterRows(rows, text, chips), sort.key, sort.dir), [rows, text, chips, sort]);
  const row = rows.find((r) => r.path === picked) ?? null;
  const title = view.kind === "format" ? view.format : TITLES.selection;
  const companions = rows.reduce((n, r) => n + r.companions, 0);

  return (
    <>
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b px-3 py-1.5">
        <h2 className="flex items-center gap-1.5 text-sm font-semibold">
          {view.kind === "format" && <i className="inline-block size-2.5 rounded-full" style={{ background: pileColor(view.format) }} />}
          {title}
        </h2>
        <span className="text-xs text-muted-foreground" data-testid="drawer-count">
          {q.isSuccess ? `${shown.length} of ${rows.length} files${companions ? ` · ${companions} companions folded` : ""}` : ""}
        </span>
        <Input aria-label="Filter files" className="h-7 w-40 min-w-0 text-xs" placeholder="Filter files…" value={text} onChange={(e) => setText(e.target.value)} />
        <span className="flex flex-wrap gap-1" role="group" aria-label="State">
          {dispositionChips(rows).map((c) => (
            <button
              key={c.id}
              type="button"
              aria-pressed={chips.has(c.id)}
              className={cn("rounded-full border px-2 py-0.5 text-xs", chips.has(c.id) ? "border-primary bg-accent-soft text-primary" : "text-muted-foreground hover:bg-accent")}
              onClick={() =>
                setChips((cur) => {
                  const next = new Set(cur);
                  if (!next.delete(c.id)) next.add(c.id);
                  return next;
                })
              }
            >
              {c.id} {c.n}
            </button>
          ))}
        </span>
        <Button variant="ghost" size="icon" className="ml-auto size-7" aria-label="Close drawer" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </header>
      <div className="flex min-h-0 flex-1">
        <div className={cn("min-w-0 flex-1 overflow-auto", row && "max-md:hidden")}>
          {!byFormat && ids.length === 0 ? (
            <div className="p-3"><Empty>Select pages first: this lists the raw files they stand on.</Empty></div>
          ) : q.isLoading ? (
            <div className="p-3"><Loading label="Loading files" rows={3} /></div>
          ) : q.isError ? (
            <div className="p-3"><ErrorState title="Could not load the files." error={q.error} onRetry={() => void q.refetch()} /></div>
          ) : rows.length === 0 ? (
            <div className="p-3"><Empty>No raw files here.</Empty></div>
          ) : (
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-card">
                <tr className="border-b">
                  {COLUMNS.map((c) => (
                    <th key={c.key} scope="col" className={cn("px-2 py-1 font-medium", c.cls)} aria-sort={sort.key === c.key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
                      <button type="button" className="hover:underline" onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? (s.dir === 1 ? -1 : 1) : 1 }))}>
                        {c.label}
                        {sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {shown.slice(0, ROW_CAP).map((r) => (
                  <tr key={r.path} className={cn("border-b last:border-0 hover:bg-accent/50", r.path === picked && "bg-accent")}>
                    <td className="max-w-[16rem] truncate px-2 py-1">
                      <button type="button" className="max-w-full truncate text-left hover:underline" title={r.path} onClick={() => setPicked(r.path)} aria-current={r.path === picked}>
                        {nameOfPath(r.path)}
                      </button>
                      {r.companions > 0 && <span className="ml-1 text-muted-foreground" title="asset / ink / duplicate files folded into this one">+{r.companions}</span>}
                    </td>
                    <td className="px-2 py-1">
                      <span className={cn("rounded px-1", canDigest(r) ? "bg-muted text-foreground" : isDigestedRow(r) ? "text-primary" : "text-muted-foreground")}>{dispositionHead(r.disposition) || "queued"}</span>
                    </td>
                    <td className="hidden max-w-[12rem] truncate px-2 py-1 text-muted-foreground sm:table-cell">{r.slug ?? ""}</td>
                    <td className="hidden px-2 py-1 text-muted-foreground md:table-cell">{r.year ?? ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {shown.length > ROW_CAP && <p className="p-2 text-xs text-muted-foreground">Showing the first {ROW_CAP}: filter to narrow.</p>}
        </div>
        {row && <FilePreview row={row} ctx={ctx} onBack={() => setPicked(null)} />}
      </div>
    </>
  );
}

/** Manifest facts, an excerpt, and the actions on one raw file. */
function FilePreview({ row, ctx, onBack }: { row: DrawerRow; ctx: GraphToolContext; onBack: () => void }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const host = useToolHost();
  const preview = useApiQuery(["raw", row.path], (d) => d.getRawPreview(row.path));
  const [confirm, setConfirm] = useState(false);
  const [note, setNote] = useState("");
  const digest = useMutation({
    mutationFn: () => ds.digestRaw(row.path),
    onSuccess: async (res) => {
      setConfirm(false);
      setNote(res.exit === 0 ? `Digested (exit 0).\n${res.stdout}` : `easy-digest exited ${res.exit}.\n${res.stderr || res.stdout}`);
      await Promise.all(["corpus", "resolve", "raw", "graph"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
    },
    onError: (e) => {
      setConfirm(false);
      setNote(`Digest failed: ${e instanceof Error ? e.message : String(e)}`);
    },
  });
  useEffect(() => {
    setConfirm(false);
    setNote("");
  }, [row.path]);

  const slug = row.slug ?? preview.data?.slug ?? null;
  const onGraph = !!slug && ctx.byId.has(slug);
  const addToDraft = () => {
    const d = activeDraft(useBasket.getState().store);
    const res = useBasket.getState().add(d ? { slug: d.slug, title: d.title, isNew: d.isNew } : UNTITLED, [toScopeRow(row)]);
    setNote(res.added ? "Added to the scope draft." : "Already in the scope draft.");
  };
  const meta: [string, string | number | null][] = [
    ["state", row.disposition],
    ["page", slug],
    ["collection", row.collection.join(", ") || null],
    ["year", row.year],
  ];

  return (
    <aside aria-label="File preview" className="flex w-full min-w-0 flex-col overflow-y-auto border-l md:w-[22rem] md:flex-none">
      <div className="flex items-center gap-1 border-b px-2 py-1 md:hidden">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft aria-hidden /> Files
        </Button>
      </div>
      <div className="flex flex-col gap-2 p-3 text-xs">
        <h3 className="break-all text-sm font-semibold">{nameOfPath(row.path)}</h3>
        <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
          {meta.filter(([, v]) => v !== null && v !== "").map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="break-words">{v}</dd>
            </div>
          ))}
        </dl>
        <div className="flex flex-wrap gap-1.5">
          {preview.data?.exists ? (
            <Button asChild size="sm" variant="outline">
              <a href={preview.data.file_url} target="_blank" rel="noopener noreferrer">Open file</a>
            </Button>
          ) : (
            preview.isSuccess && <span className="text-muted-foreground">File not on disk here.</span>
          )}
          {onGraph && (
            <Button size="sm" variant="outline" onClick={() => ctx.focus(slug as string)}>
              Show in graph
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={addToDraft}>
            Add to scope draft
          </Button>
          <Button asChild size="sm" variant="outline">
            <a
              href={host.href("/pipeline", { item: row.path })}
              onClick={(e) => {
                e.preventDefault();
                host.go("/pipeline", { item: row.path });
              }}
            >
              Open in Pipeline
            </a>
          </Button>
        </div>
        {canDigest(row) ? (
          confirm ? (
            <div className="flex flex-col gap-1.5 rounded-md border p-2" role="alertdialog" aria-label="Confirm easy-digest">
              <p>Run easy-digest on this file? It writes a source page into the vault (one undoable step).</p>
              <div className="flex gap-1.5">
                <Button size="sm" disabled={digest.isPending} onClick={() => digest.mutate()}>
                  {digest.isPending ? "Running…" : "Run easy-digest"}
                </Button>
                <Button size="sm" variant="ghost" disabled={digest.isPending} onClick={() => setConfirm(false)}>
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-1.5">
              <Button size="sm" onClick={() => setConfirm(true)}>
                Easy-digest…
              </Button>
              <a
                className="text-primary hover:underline"
                href={host.href("/chat", { q: `full-digest ${row.path}` })}
                onClick={(e) => {
                  e.preventDefault();
                  host.go("/chat", { q: `full-digest ${row.path}` });
                }}
              >
                Full or deep digest in Chat
              </a>
            </div>
          )
        ) : null}
        {note && (
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-muted p-2" role="status">
            {note}
          </pre>
        )}
        {preview.isLoading && <Loading label="Loading preview" rows={2} />}
        {preview.isError &&
          (preview.error instanceof ApiError && preview.error.status === 404 ? (
            <p className="text-muted-foreground">File not on disk here, so there is no excerpt.</p>
          ) : (
            <ErrorState title="Preview failed." error={preview.error} onRetry={() => void preview.refetch()} />
          ))}
        {preview.data && (
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-muted p-2">{preview.data.text || preview.data.error || "(no text excerpt)"}</pre>
        )}
      </div>
    </aside>
  );
}
