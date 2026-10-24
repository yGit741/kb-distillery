import { ExternalLink, X } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/useApiQuery";

/**
 * The page next to the graph, read without leaving it. Uses the shared <Markdown> over /api/pages/{slug}
 * (no second renderer, no iframe), so it works whether or not the Pages screen has an embed mode.
 */
export function SideReader({ slug, title, pageHref, onClose }: { slug: string; title: string; pageHref: string; onClose: () => void }) {
  const q = useApiQuery(["page", slug], (ds) => ds.getPage(slug));
  return (
    <aside
      aria-label="Page reader"
      className="pointer-events-auto absolute inset-y-0 right-0 z-30 flex w-[min(34rem,100%)] flex-col border-l bg-card text-card-foreground shadow-[var(--shadow)]"
    >
      <header className="flex items-center gap-2 border-b px-3 py-2">
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
          <Markdown>{q.data.markdown}</Markdown>
        ) : (
          <Empty>This page has no text yet.</Empty>
        )}
      </div>
    </aside>
  );
}
