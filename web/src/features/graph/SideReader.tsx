import { ExternalLink, X } from "lucide-react";
import { useMemo } from "react";
import { Markdown } from "@/components/Markdown";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/useApiQuery";
import { NodeMarkSvg } from "./encoding";

/**
 * The page next to the graph, read without leaving it. Uses the shared <Markdown> over /api/pages/{slug}
 * (no second renderer, no iframe), so it works whether or not the Pages screen has an embed mode.
 */
export function SideReader({ slug, kb, title, pageHref, onClose }: { slug: string; kb?: string; title: string; pageHref: string; onClose: () => void }) {
  // `kb` is the node's knowledge base; the server's own answers as usual, another one read-only
  const q = useApiQuery(["page", slug, kb ?? ""], (ds) => (kb ? ds.getPage(slug, { kb }) : ds.getPage(slug)));
  const linkSearch = useMemo(() => (kb ? { kb } : undefined), [kb]);
  return (
    <aside
      aria-label="Page reader"
      data-tour="page-reader"
      className="pointer-events-auto absolute inset-y-0 right-0 z-30 flex w-[min(34rem,100%)] flex-col border-l bg-card text-card-foreground shadow-[var(--shadow)]"
    >
      <header className="flex items-center gap-2 border-b px-3 py-2">
        {/* the page's mark; its slot is reserved, so the title never shifts when the page loads */}
        <span aria-hidden title={q.data?.card.type} className="inline-flex size-4 shrink-0 text-muted-foreground">
          {q.data?.card.type && <NodeMarkSvg type={q.data.card.type} className="size-4" />}
        </span>
        <h2 className="min-w-0 flex-1 truncate text-sm font-semibold">{q.data?.card.title || title}</h2>
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
