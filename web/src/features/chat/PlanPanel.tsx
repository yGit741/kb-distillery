import { Check, Circle, CircleDot, ListChecks } from "lucide-react";
import { useSyncExternalStore } from "react";
import { cn } from "@/lib/utils";
import type { TodoItem } from "./sse";

/**
 * The agent's plan (its latest TodoWrite list; each event replaces the last), flag `agent-mode`.
 * On wide screens it sits at the top of the session rail beside the stream; below that it keeps the composer slot.
 * Each placement renders itself only where it belongs, so the list is in the page once.
 */

const WIDE = "(min-width: 1024px)";

function subscribeWide(cb: () => void) {
  const mq = window.matchMedia?.(WIDE);
  mq?.addEventListener?.("change", cb);
  return () => mq?.removeEventListener?.("change", cb);
}
const isWide = () => window.matchMedia?.(WIDE).matches ?? false;
/** True from the `lg` breakpoint up, where the session rail is shown (the same breakpoint as ChatScreen's grid). */
export const useWide = () => useSyncExternalStore(subscribeWide, isWide, () => false);

const STATUS = {
  pending: { Icon: Circle, label: "pending" },
  in_progress: { Icon: CircleDot, label: "in progress" },
  completed: { Icon: Check, label: "done" },
} as const;

export function PlanPanel({ items, busy, placement }: { items: TodoItem[]; busy: boolean; placement: "rail" | "inline" | "header" }) {
  const wide = useWide();
  // "header" (the full chat's column header, flag `chat-full`) shows at any width
  if (placement !== "header" && wide !== (placement === "rail")) return null;
  // nothing to show: no plan yet, or every step is done and the turn is over
  if (!items.length || (!busy && items.every((t) => t.status === "completed"))) return null;
  const done = items.filter((t) => t.status === "completed").length;
  return (
    <section className="rounded-md border bg-card p-3 text-sm" data-testid="plan-panel" data-placement={placement}>
      <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
        <ListChecks aria-hidden className="size-4 shrink-0" />
        Plan
        <span className="ml-auto text-xs font-normal text-muted-foreground">
          {done} of {items.length} done
        </span>
      </h2>
      <ul className="flex flex-col gap-1.5">
        {items.map((t, i) => {
          const { Icon, label } = STATUS[t.status];
          return (
            <li
              key={i}
              data-status={t.status}
              className={cn("flex items-start gap-2", t.status === "completed" && "text-muted-foreground line-through", t.status === "in_progress" && "font-medium")}
            >
              <Icon aria-hidden className="mt-0.5 size-4 shrink-0" />
              <span className="sr-only">{label}: </span>
              <span className="min-w-0 break-words">{t.content}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
