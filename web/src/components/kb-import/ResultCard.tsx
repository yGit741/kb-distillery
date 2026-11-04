import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * The outcome card of an import: a title, one line of detail and an optional action. `done` is a finished result
 * (imported, open it); `pending` is a handover (received, it appears after your Mac's next sync).
 */
export function ResultCard({ tone, title, children, action }: { tone: "done" | "pending"; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div role="status" className={cn("flex flex-col gap-2 rounded-lg border p-4", tone === "done" ? "border-ok" : "")}>
      <p className={cn("text-sm font-medium", tone === "done" && "text-ok")}>{title}</p>
      {children && <div className="text-sm text-muted-foreground">{children}</div>}
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}
