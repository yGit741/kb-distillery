/**
 * Backlog screen: the local `.backlog/` cards (send-to-backlog skill), read-only, grouped by status.
 * A plan card says whether it has a plan file and, from git alone, whether the plan is still relevant.
 * Local app only: this folder is not listed in the share builds, so it is not in those bundles.
 */
import type { BacklogItem } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";

export const ported = true;

const STATUS_ORDER = ["inbox", "next", "doing", "done", "dropped"] as const;
const STATUS_LABEL: Record<(typeof STATUS_ORDER)[number], string> = {
  inbox: "Inbox",
  next: "Next",
  doing: "Doing",
  done: "Done",
  dropped: "Dropped",
};
const SIZE_LABEL: Record<string, string> = { s: "Small", m: "Medium", l: "Large" };

/** The relevance chip of a plan card. Neutral when fine; amber only when the plan needs a second look. */
export function driftChip(item: BacklogItem): { text: string; variant: "outline" | "warn"; title: string } | null {
  const d = item.drift;
  if (item.plan_status !== "has-plan" || d.level === "none" || d.level === "closed") return null;
  if (d.level === "maybe-done")
    return { text: "May be done", variant: "warn", title: `Later commits match this title:\n${d.maybe_done.join("\n")}` };
  if (d.level === "stale")
    return {
      text: "Stale",
      variant: "warn",
      title: d.missing.length ? `Paths gone or renamed:\n${d.missing.join("\n")}` : `${d.commits} commits touched its paths`,
    };
  if (d.level === "drifted")
    return { text: `${d.commits} ${d.commits === 1 ? "commit" : "commits"} since`, variant: "outline", title: "Commits touched the paths this plan names" };
  return { text: "Up to date", variant: "outline", title: "Nothing touched the paths this plan names" };
}

function BacklogCard({ item }: { item: BacklogItem }) {
  const chip = driftChip(item);
  return (
    <Card>
      <CardContent className="flex flex-col gap-2 p-4">
        <p className="font-medium leading-snug">{item.title}</p>
        {item.why && <p className="text-sm text-muted-foreground">{item.why}</p>}
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge>{item.kind}</Badge>
          {item.area && <Badge variant="outline">{item.area}</Badge>}
          <Badge variant="outline">{SIZE_LABEL[item.size] ?? item.size}</Badge>
          <Badge variant="outline">{item.plan_status === "has-plan" ? "Has plan" : "No plan"}</Badge>
          {chip && (
            <Badge variant={chip.variant} title={chip.title}>
              {chip.text}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          {item.created}
          {item.source ? ` · ${item.source}` : ""}
        </p>
      </CardContent>
    </Card>
  );
}

export default function BacklogScreen() {
  const list = useApiQuery(["backlog"], (d) => d.listBacklog());
  const items = list.data?.items ?? [];

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">Backlog</h1>
        <p className="text-sm text-muted-foreground">
          Ideas, bugs and unstarted plans. Add one by asking Claude to send it to the backlog.
        </p>
      </header>
      {list.isPending && <Loading label="Loading backlog" />}
      {list.isError && <ErrorState title="Could not load the backlog" error={list.error} onRetry={() => void list.refetch()} />}
      {list.isSuccess && items.length === 0 && <Empty>Nothing parked yet.</Empty>}
      {list.isSuccess &&
        STATUS_ORDER.map((status) => {
          const group = items.filter((i) => i.status === status);
          if (group.length === 0) return null;
          return (
            <section key={status} aria-label={STATUS_LABEL[status]} className="flex flex-col gap-3">
              <h2 className="text-sm font-medium text-muted-foreground">
                {STATUS_LABEL[status]} · {group.length}
              </h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {group.map((i) => (
                  <BacklogCard key={i.id} item={i} />
                ))}
              </div>
            </section>
          );
        })}
    </main>
  );
}
