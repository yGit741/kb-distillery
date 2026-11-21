import { cn } from "@/lib/utils";
import type { ArtifactIndex, Crumb } from "./model";
import { EVIDENCE } from "./model";

/**
 * The three layers in one row over the page types at the bottom of the graph: Concepts (the pages), the template's artifact views, and
 * Evidence (the pages beside the code their facts cite). Under a view that nests, the path drilled into, each step
 * a way back up. Shown only when the knowledge base has an artifact layer.
 */
export function ArtifactBar({
  ix,
  code,
  crumbs,
  hidden,
  onGo,
}: {
  ix: ArtifactIndex;
  code: string | null;
  crumbs: readonly Crumb[];
  hidden: number;
  onGo: (code: string | null, at?: string | null) => void;
}) {
  const cited = ix.pageNodes.size;
  const pill = (on: boolean) =>
    cn("shrink-0 rounded-full px-2.5 py-0.5 text-xs transition-colors", on ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground");
  return (
    <div data-testid="artifact-bar" className="pointer-events-none absolute inset-x-0 bottom-10 z-10 flex flex-col items-center gap-1 px-3">
      {code && code !== EVIDENCE && crumbs.length > 1 && (
        <nav aria-label="Drilled into" className="pointer-events-auto flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full border bg-card/95 px-2 py-0.5 text-xs shadow-[var(--shadow)]">
          {crumbs.map((c, i) => {
            const last = i === crumbs.length - 1;
            return (
              <span key={c.id ?? "top"} className="flex shrink-0 items-center gap-0.5">
                {i > 0 && <span className="text-muted-foreground/60">/</span>}
                <button type="button" disabled={last} className={cn("rounded px-1", last ? "font-medium" : "text-muted-foreground hover:bg-accent hover:text-foreground")} onClick={() => onGo(code, c.id)}>
                  {c.name}
                </button>
              </span>
            );
          })}
          {hidden > 0 && <span className="ml-1 shrink-0 text-muted-foreground" title="Inside, but no link of this view reaches them">· {hidden} unlinked</span>}
        </nav>
      )}
      <div role="tablist" aria-label="Layers" className="pointer-events-auto flex max-w-full items-center gap-0.5 overflow-x-auto rounded-full border bg-card/95 p-0.5 shadow-[var(--shadow)]">
        <button type="button" role="tab" aria-selected={!code} className={pill(!code)} title="The concept pages and their links" onClick={() => onGo(null)}>
          Concepts
        </button>
        <span className="mx-0.5 h-4 w-px shrink-0 bg-border" aria-hidden />
        {ix.views.map((v) => (
          <button key={v.id} type="button" role="tab" aria-selected={code === v.id} className={pill(code === v.id)} title={v.hint || v.name} onClick={() => onGo(v.id, null)}>
            {v.name}
          </button>
        ))}
        {cited > 0 && (
          <>
            <span className="mx-0.5 h-4 w-px shrink-0 bg-border" aria-hidden />
            <button type="button" role="tab" aria-selected={code === EVIDENCE} className={pill(code === EVIDENCE)} title={`The ${cited} pages that cite code, beside the files their facts are about`} onClick={() => onGo(EVIDENCE)}>
              Evidence
            </button>
          </>
        )}
      </div>
    </div>
  );
}
