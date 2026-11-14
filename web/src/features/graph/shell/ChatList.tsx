import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { chatWhen, defaultFetch, listSessions, type SessionRow } from "./corners/api";
import { browserSessions, loadSession, newChat } from "./corners/sessions";
import { BUSY_NOTICE, useChatFull } from "./chatFullStore";
import { useSparkPanel } from "./sparkPanelStore";

/** Whether a chat may be swapped now: an answer streaming in the panel would be aborted by the remount. */
function mayLeave(): boolean {
  if (!useChatFull.getState().busy) return true;
  useChatFull.getState().setNotice(BUSY_NOTICE);
  return false;
}

const plain = (id: string) => id.replace(/^kb-chat:/, "");
const REFRESH_MS = 8000;

/** Group the rows: pinned first, then chats of today (and any that is doing something now), then the rest. */
export function groupChats(rows: readonly SessionRow[], now = new Date()): { label: string; rows: SessionRow[] }[] {
  const pinned = rows.filter((r) => r.pinned);
  const rest = rows.filter((r) => !r.pinned);
  const isToday = (r: SessionRow) => r.status === "running" || r.status === "waiting" || r.status === "error" || chatWhen(r, now) === "today";
  const groups = [
    { label: "Pinned", rows: pinned },
    { label: "Today", rows: rest.filter(isToday) },
    { label: "Earlier", rows: rest.filter((r) => !isToday(r)) },
  ];
  return groups.filter((g) => g.rows.length);
}

/**
 * The chat list of the full chat (flag `chat-full`): the spark fan grown into a column. New chat, Pinned, Today and
 * Earlier, each row with its status or day. A click opens that chat in the chat column next to it.
 */
export function ChatList({ activeId, server, limit, onMore }: { activeId: string; server: boolean; limit?: number; onMore?: () => void }) {
  const q = useQuery({
    queryKey: ["corners", "sessions"],
    queryFn: () => listSessions(defaultFetch),
    enabled: server,
    staleTime: 0,
    retry: false,
    refetchInterval: REFRESH_MS,
  });
  const rows = useMemo<SessionRow[]>(() => q.data ?? browserSessions(), [q.data]);
  // a pinned chat always shows; the newest of the rest fill the limit
  const shown = useMemo(() => {
    if (!limit) return rows;
    const pinned = rows.filter((r) => r.pinned);
    return [...pinned, ...rows.filter((r) => !r.pinned).slice(0, Math.max(0, limit - pinned.length))];
  }, [rows, limit]);
  const groups = useMemo(() => groupChats(shown), [shown]);
  const compact = limit !== undefined;
  const open = (row: SessionRow) => {
    if (plain(row.id) === plain(activeId) || !mayLeave()) return;
    void (async () => {
      try {
        if (q.data) await loadSession(defaultFetch, row.id);
        useSparkPanel.getState().show();
      } catch {
        void q.refetch();
      }
    })();
  };
  return (
    <nav
      aria-label={compact ? "Recent chats" : "Chats"}
      data-testid={compact ? "recent-chats" : "chat-list"}
      className={cn("flex w-full min-w-0 flex-col gap-4", compact ? "mt-6" : "h-full overflow-y-auto bg-background px-2 py-3")}
    >
      {!compact && (
      <button
        type="button"
        onClick={() => mayLeave() && newChat()}
        className="flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Plus aria-hidden className="size-4 shrink-0" strokeWidth={1.6} />
        New chat
      </button>
      )}
      {q.isPending && server && <p className="px-2.5 text-xs text-muted-foreground">Loading chats</p>}
      {!q.isPending && !groups.length && !compact && <p className="px-2.5 text-xs text-muted-foreground">No saved chats yet.</p>}
      {groups.map((g) => (
        <section key={g.label} aria-label={g.label} className="flex flex-col gap-0.5">
          <h3 className="px-2.5 pb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{g.label}</h3>
          {g.rows.map((r) => {
            const active = plain(r.id) === plain(activeId);
            const when = chatWhen(r);
            return (
              <button
                key={r.id}
                type="button"
                title={r.title}
                aria-current={active ? "true" : undefined}
                onClick={() => open(r)}
                className={cn(
                  "flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active ? "bg-card shadow-[var(--shadow)]" : "hover:bg-secondary",
                )}
              >
                {r.status === "running" && <span aria-hidden className="size-1.5 shrink-0 rounded-full bg-ok" />}
                <span className="min-w-0 flex-1 truncate">{r.title}</span>
                {when && <small className="shrink-0 text-[11px] text-muted-foreground">{when}</small>}
              </button>
            );
          })}
        </section>
      ))}
      {compact && onMore && rows.length > shown.length && (
        <button
          type="button"
          data-testid="all-chats"
          onClick={onMore}
          className="self-start rounded-lg px-2.5 py-1 text-xs text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          All chats ({rows.length})
        </button>
      )}
    </nav>
  );
}
