import { Button } from "@/components/ui/button";
import type { GNode } from "../types";
import { permalink, placeOf, type ArtifactIndex } from "./model";

const SHOWN = 8;

/**
 * The selected artifact: what and where it is, its line at its source host, a way inside it, and the pages whose facts are
 * about it (or about anything inside it). A page opens back on the concept graph, focused.
 */
export function ArtifactCard({
  ix,
  id,
  pages,
  canDrill,
  onDrill,
  onPage,
  onClear,
}: {
  ix: ArtifactIndex;
  id: string;
  /** the concept pages by slug, for their titles */
  pages: ReadonlyMap<string, GNode>;
  canDrill: boolean;
  onDrill: (id: string) => void;
  onPage: (slug: string) => void;
  onClear: () => void;
}) {
  const n = ix.byId.get(id);
  if (!n) return null;
  const href = permalink(ix.graph, n);
  const kids = ix.children.get(id)?.length ?? 0;
  const citing = [...(ix.citedBy.get(id) ?? [])].filter((s) => pages.has(s));
  const facts = [...ix.factNodes].filter(([, ids]) => ids.has(id)).length;
  return (
    <div
      data-testid="artifact-card"
      className="pointer-events-auto absolute bottom-32 left-1/2 z-20 w-[min(24rem,calc(100%-2rem))] -translate-x-1/2 rounded-xl border bg-card p-3 text-sm shadow-[var(--shadow)]"
    >
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{n.type}</div>
          <div className="truncate font-medium" title={n.name}>
            {n.name || n.id}
          </div>
          {placeOf(n) && <div className="truncate font-mono text-xs text-muted-foreground" title={placeOf(n)}>{placeOf(n)}</div>}
        </div>
        <button type="button" aria-label="Clear selection" className="shrink-0 rounded px-1 text-muted-foreground hover:bg-accent" onClick={onClear}>
          ×
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {href && (
          <Button size="sm" variant="outline" asChild>
            <a href={href} target="_blank" rel="noreferrer">
              Open the code
            </a>
          </Button>
        )}
        {canDrill && (
          <Button size="sm" variant="outline" onClick={() => onDrill(id)}>
            Inside ({kids})
          </Button>
        )}
      </div>
      <div className="mt-2 text-xs text-muted-foreground">
        {citing.length ? `Cited by ${citing.length} page${citing.length === 1 ? "" : "s"}${facts ? ` · ${facts} fact${facts === 1 ? "" : "s"} about it` : ""}` : facts ? `${facts} fact${facts === 1 ? "" : "s"} about it, no page cites them yet` : "No page cites it yet"}
      </div>
      {citing.length > 0 && (
        <ul className="mt-1 flex flex-wrap gap-1">
          {citing.slice(0, SHOWN).map((s) => (
            <li key={s}>
              <button type="button" className="rounded-full border px-2 py-0.5 text-xs hover:bg-accent" onClick={() => onPage(s)}>
                {pages.get(s)?.title || s}
              </button>
            </li>
          ))}
          {citing.length > SHOWN && <li className="px-1 py-0.5 text-xs text-muted-foreground">+{citing.length - SHOWN} more</li>}
        </ul>
      )}
    </div>
  );
}
