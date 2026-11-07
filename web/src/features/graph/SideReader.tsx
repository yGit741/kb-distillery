import { ChevronLeft, ChevronRight, ExternalLink, X } from "lucide-react";
import { useEffect, useMemo } from "react";
import { Markdown } from "@/components/Markdown";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/useApiQuery";
import { NodeMarkSvg } from "./encoding";
import { LINE_COPY } from "./shell/copy";

/** Where the reader is in a set of pages: 1-based `index` of `total`, and a move by one. */
export interface ReaderStep {
  index: number;
  total: number;
  go: (delta: -1 | 1) => void;
}

/**
 * The page next to the graph, read without leaving it. Uses the shared <Markdown> over /api/pages/{slug}
 * (no second renderer, no iframe), so it works whether or not the Pages screen has an embed mode. `inline` (flag
 * `chat-full`) fills its parent instead of floating: the mini explorer under the graph.
 */
export function SideReader({ slug, kb, title, pageHref, onClose, inline, step }: { slug: string; kb?: string; title: string; pageHref: string; onClose: () => void; inline?: boolean; step?: ReaderStep }) {
  // `kb` is the node's knowledge base; the server's own answers as usual, another one read-only
  const q = useApiQuery(["page", slug, kb ?? ""], (ds) => (kb ? ds.getPage(slug, { kb }) : ds.getPage(slug)));
  // [ and ] move through a set, unless a field has the keys
  const go = step?.go;
  useEffect(() => {
    if (!go) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const t = e.target;
      if (t instanceof HTMLElement && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
      if (e.key === "[") go(-1);
      else if (e.key === "]") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);
  const linkSearch = useMemo(() => (kb ? { kb } : undefined), [kb]);
  return (
    <aside
      aria-label="Page reader"
      data-tour="page-reader"
      className={
        inline
          ? "pointer-events-auto flex size-full min-w-0 flex-col bg-card text-card-foreground"
          : "pointer-events-auto absolute inset-y-0 right-0 z-30 flex w-[min(34rem,100%)] flex-col border-l bg-card text-card-foreground shadow-[var(--shadow)]"
      }
    >
      <header className="flex items-center gap-2 border-b px-3 py-2">
        {/* the page's mark; its slot is reserved, so the title never shifts when the page loads */}
        <span aria-hidden title={q.data?.card.type} className="inline-flex size-4 shrink-0 text-muted-foreground">
          {q.data?.card.type && <NodeMarkSvg type={q.data.card.type} className="size-4" />}
        </span>
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">{q.data?.card.title || title}</h2>
        {step && step.total > 1 && (
          <nav aria-label={LINE_COPY.reader.nav} className="flex items-center gap-0.5 text-xs text-muted-foreground">
            <Button variant="ghost" size="icon" className="size-7" aria-label={LINE_COPY.reader.prev} title="[" disabled={step.index <= 1} onClick={() => step.go(-1)}>
              <ChevronLeft aria-hidden />
            </Button>
            <span className="min-w-12 text-center tabular-nums">{LINE_COPY.reader.of(step.index, step.total)}</span>
            <Button variant="ghost" size="icon" className="size-7" aria-label={LINE_COPY.reader.next} title="]" disabled={step.index >= step.total} onClick={() => step.go(1)}>
              <ChevronRight aria-hidden />
            </Button>
          </nav>
        )}
        <Button asChild variant="secondary" size="sm">
          <a href={pageHref}>
            Open full page <ExternalLink aria-hidden />
          </a>
        </Button>
        <Button variant="ghost" size="icon" className="size-8" aria-label="Close reader" onClick={onClose}>
          <X aria-hidden />
        </Button>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {q.isLoading ? (
          <Loading label="Loading page" rows={4} />
        ) : q.isError ? (
          <ErrorState title="Could not load this page." error={q.error} onRetry={() => void q.refetch()} />
        ) : q.data?.markdown ? (
          <Markdown linkSearch={linkSearch}>{q.data.markdown}</Markdown>
        ) : (
          <Empty>This page has no text yet.</Empty>
        )}
      </div>
    </aside>
  );
}
