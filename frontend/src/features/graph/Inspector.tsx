import { X } from "lucide-react";
import { useMemo } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Swatch } from "./controls";
import { sourcesOf, type NeighborMap } from "./graphData";
import { LAYER_LABEL } from "./legendModel";
import { colorOf, type ColorBy } from "./style";
import { bookOf, degreeOf, partOf, type GNode } from "./types";
import type { Layer } from "@/api/model";

const NB_MAX = 40;
export const obsidianUri = (path: string) => `obsidian://open?file=${encodeURIComponent(path)}`;

interface Props {
  nodes: readonly GNode[];
  byId: ReadonlyMap<string, GNode>;
  neighbors: NeighborMap;
  colorBy: ColorBy;
  revealed: ReadonlySet<string>;
  pageHref: (slug: string) => string;
  onClose: () => void;
  onClear: () => void;
  onFocus: (id: string, zoom?: boolean) => void;
  onRead: (id: string) => void;
  onToggleSources: (ids: string[]) => void;
}

function Row({ n, colorBy, onGo, children }: { n: GNode; colorBy: ColorBy; onGo: () => void; children?: React.ReactNode }) {
  return (
    <li>
      <button type="button" className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-sm hover:bg-accent" onClick={onGo}>
        <Swatch color={colorOf(n, colorBy)} />
        <span className="min-w-0 flex-1 truncate">{n.title || n.id}</span>
        {children}
      </button>
    </li>
  );
}

/** The selected page(s): what it is, its summary, and (collapsed) its partition, connections and properties. */
export function Inspector(p: Props) {
  const { nodes } = p;
  if (!nodes.length) return null;
  return (
    <aside
      aria-label="Selected page"
      className="pointer-events-auto absolute bottom-3 right-3 z-20 flex max-h-[62%] w-[min(24rem,calc(100%-1.5rem))] flex-col rounded-lg border bg-card text-card-foreground shadow-[var(--shadow)] max-sm:left-3 max-sm:w-auto"
    >
      <Button variant="ghost" size="icon" className="absolute right-1 top-1 size-7" aria-label="Close details" onClick={p.onClose}>
        <X aria-hidden />
      </Button>
      {nodes.length > 1 ? <Many {...p} /> : <One {...p} n={nodes[0] as GNode} />}
    </aside>
  );
}

function Many({ nodes, byId: _b, colorBy, onFocus, onClear }: Props) {
  return (
    <div className="flex flex-col gap-2 overflow-y-auto p-3 pr-9">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">Selection</div>
      <h2 className="text-base font-semibold">{nodes.length} pages selected</h2>
      <Button variant="secondary" size="sm" className="self-start" onClick={onClear}>
        Clear selection
      </Button>
      <ul>
        {nodes.slice(0, NB_MAX).map((n) => (
          <Row key={n.id} n={n} colorBy={colorBy} onGo={() => onFocus(n.id, false)} />
        ))}
      </ul>
      {nodes.length > NB_MAX && <p className="text-xs text-muted-foreground">…and {nodes.length - NB_MAX} more</p>}
    </div>
  );
}

function One({ n, byId, neighbors, colorBy, revealed, pageHref, onFocus, onRead, onToggleSources }: Props & { n: GNode }) {
  const nbs = useMemo(
    () =>
      (neighbors.get(n.id) ?? [])
        .map((id) => byId.get(id))
        .filter((m): m is GNode => !!m)
        .sort((a, b) => degreeOf(b) - degreeOf(a)),
    [neighbors, byId, n.id],
  );
  const sources = n.layer === "source" ? [] : sourcesOf(n.id, neighbors, byId);
  const sourcesOn = sources.length > 0 && sources.every((s) => revealed.has(s));
  const part = partOf(n);
  const book = bookOf(n);
  const pct = book && book.content ? Math.round((100 * book.done) / book.content) : 0;
  const layerLabel = n.layer ? LAYER_LABEL[n.layer as Layer]?.replace(/s$/, "").toLowerCase() ?? n.layer : "";
  return (
    <div className="flex flex-col gap-2.5 overflow-y-auto p-3 pr-9">
      <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
        <Swatch color={colorOf(n, colorBy)} />
        <span>{layerLabel ? `${layerLabel} · ${n.type}` : n.type}</span>
        {n.depth && <Badge variant="primary">{n.depth}</Badge>}
        {n.status && <Badge>{n.status}</Badge>}
        {n.year ? <span>{n.year}</span> : null}
        {part?.pages && <span>pp. {part.pages.replace("-", "–")}</span>}
        {n.areas.slice(0, 3).map((a) => (
          <span key={a}>#{a}</span>
        ))}
      </div>
      <h2 className="text-base font-semibold leading-snug">{n.title || n.id}</h2>
      <div className="flex flex-wrap gap-1.5">
        <Button size="sm" onClick={() => onRead(n.id)}>
          Read
        </Button>
        <Button asChild variant="secondary" size="sm">
          <a href={pageHref(n.id)}>Open in Pages</a>
        </Button>
        <Button variant="secondary" size="sm" onClick={() => onFocus(n.id)}>
          Centre
        </Button>
        {sources.length > 0 && (
          <Button variant="secondary" size="sm" aria-pressed={sourcesOn} onClick={() => onToggleSources(sources)}>
            {sourcesOn ? "Hide" : "See"} sources ({sources.length})
          </Button>
        )}
        <Button asChild variant="ghost" size="sm">
          <a href={obsidianUri(n.path || `wiki/${n.id}.md`)}>Obsidian</a>
        </Button>
      </div>
      <p className={n.preview ? "text-sm leading-relaxed" : "text-sm text-muted-foreground"}>
        {n.preview || "No summary yet: this page is still a stub."}
      </p>
      {part?.book && byId.get(part.book) && (
        <details className="rounded-md border px-2 py-1" open>
          <summary className="cursor-pointer text-sm font-medium">Part of</summary>
          <ul>
            <Row n={byId.get(part.book) as GNode} colorBy={colorBy} onGo={() => onFocus(part.book, false)} />
          </ul>
        </details>
      )}
      {book && (
        <details className="rounded-md border px-2 py-1">
          <summary className="cursor-pointer text-sm font-medium">
            Partition · {book.done}/{book.content} pp · {pct}%
          </summary>
          <div className="my-1.5 h-1.5 overflow-hidden rounded bg-secondary" aria-hidden>
            <div className="h-full bg-primary" style={{ width: `${pct}%` }} />
          </div>
          <ul>
            {book.parts
              .filter((q) => q.status !== "skip")
              .map((q) => {
                const m = q.slug ? byId.get(q.slug) : undefined;
                const pages = `p.${q.start}–${q.end}`;
                return m ? (
                  <Row key={q.start} n={{ ...m, title: q.title }} colorBy={colorBy} onGo={() => onFocus(m.id, false)}>
                    <small className="text-muted-foreground">
                      {pages} · {q.status}
                    </small>
                  </Row>
                ) : (
                  <li key={q.start} className="flex gap-2 px-1.5 py-1 text-sm text-muted-foreground">
                    <span className="min-w-0 flex-1 truncate">{q.title}</span>
                    <small>{pages}</small>
                  </li>
                );
              })}
          </ul>
        </details>
      )}
      <details className="rounded-md border px-2 py-1">
        <summary className="cursor-pointer text-sm font-medium">
          Connected pages · {n.inDegree}↘ {n.outDegree}↗
        </summary>
        {nbs.length ? (
          <ul>
            {nbs.slice(0, NB_MAX).map((m) => (
              <Row key={m.id} n={m} colorBy={colorBy} onGo={() => onFocus(m.id, false)} />
            ))}
          </ul>
        ) : (
          <p className="py-1 text-sm text-muted-foreground">No links yet.</p>
        )}
        {nbs.length > NB_MAX && <p className="pb-1 text-xs text-muted-foreground">…and {nbs.length - NB_MAX} more: open the page to see all.</p>}
      </details>
      <details className="rounded-md border px-2 py-1">
        <summary className="cursor-pointer text-sm font-medium">Properties</summary>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 py-1 text-xs">
          {Object.entries(n.properties).map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="break-words">
                {/^https?:\/\//i.test(v) ? (
                  <a className="text-primary underline" href={v} target="_blank" rel="noopener noreferrer">
                    {v}
                  </a>
                ) : (
                  v
                )}
              </dd>
            </div>
          ))}
        </dl>
      </details>
      <p className="text-xs text-muted-foreground">Double-click reads the page · E opens it in Pages · Esc closes</p>
    </div>
  );
}
