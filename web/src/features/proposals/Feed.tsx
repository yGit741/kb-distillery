import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import type { FeedItem } from "@/api";
import { useDataSource } from "@/api";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/useApiQuery";
import { classLabel, undoBlocker } from "./model";
import { ClassChips, when } from "./Inbox";

function FeedRow({ item }: { item: FeedItem }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const undo = useMutation({
    mutationFn: () => ds.undoProposal(item.id),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["proposals"] });
      void qc.invalidateQueries({ queryKey: ["proposal", item.id] });
    },
  });
  const undone = item.status === "undone";
  const reason = !undone && !item.undoable ? undoBlocker(item.blocked_by) : "";
  const classes = Object.fromEntries(item.classes.map((c) => [c, 1]));
  return (
    <li className="flex items-start gap-3 py-3" data-testid="feed-row" data-id={item.id}>
      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        <div className="flex items-baseline gap-3">
          <Link to={`/proposals/${encodeURIComponent(item.id)}` as "/"} className="min-w-0 truncate font-medium hover:underline">
            {item.title}
          </Link>
          <span className="shrink-0 text-xs text-muted-foreground">{undone ? "undone" : item.auto ? "auto-applied" : "applied"}</span>
          <span className="ml-auto shrink-0 whitespace-nowrap text-xs text-muted-foreground">{when(undone && item.undone_at ? item.undone_at : item.applied_at)}</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="min-w-0 truncate" title={item.pages.join(", ")}>{item.pages.join(", ")}</span>
          <span>{item.hunks} {item.hunks === 1 ? "change" : "changes"}</span>
          <ClassChips classes={classes} />
          {item.commit && <span className="font-mono">{item.commit.slice(0, 7)}</span>}
        </div>
        {reason && <p id={`why-${item.id}`} className="text-xs text-muted-foreground" data-testid="undo-reason">{reason}</p>}
        {undo.error && <p role="alert" className="text-xs text-bad">{undo.error instanceof Error ? undo.error.message : String(undo.error)}</p>}
      </div>
      {!undone && (
        <Button variant="outline" size="sm" disabled={!item.undoable || undo.isPending} aria-describedby={reason ? `why-${item.id}` : undefined} onClick={() => undo.mutate()}>
          {undo.isPending ? "Undoing" : "Undo"}
        </Button>
      )}
    </li>
  );
}

/** What was applied (by the agent or by you) and what was undone, newest first, each with one-click Undo. */
export function FeedList() {
  const q = useApiQuery(["proposals", "feed"], (ds) => ds.getProposalFeed());
  if (q.isLoading) return <Loading label="Loading the feed" />;
  if (q.error) return <ErrorState title="Could not load the feed" error={q.error} onRetry={() => void q.refetch()} />;
  const items = q.data?.feed ?? [];
  if (!items.length) return <Empty>Nothing has been applied yet.</Empty>;
  const kinds = [...new Set(items.flatMap((i) => i.classes))];
  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">{items.length} applied or undone{kinds.length ? ` · ${kinds.map(classLabel).join(", ").toLowerCase()}` : ""}</p>
      <ul className="divide-y" aria-label="Applied proposals">
        {items.map((i) => <FeedRow key={i.id} item={i} />)}
      </ul>
    </div>
  );
}
