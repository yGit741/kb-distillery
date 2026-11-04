import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, MessageSquare, Pencil, Trash2, X } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";
import { useDataSource, type SessionSummary } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useFlag } from "@/flags/useFlag";
import { fmtUsd } from "./format";
import { DELETED_EVENT, FAILED_EVENT, OPEN_EVENT, SYNCED_EVENT, chatBusy, serverSessionsOn, sessionBus, subscribeChatBusy } from "./serverStorage";

export const SESSIONS_KEY = ["chat", "sessions"] as const;

const when = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

/** Past chats kept on this machine (flag `agent-mode`): open, rename, delete. Renders nothing with the flag off. */
export function PastChats() {
  const ds = useDataSource();
  const on = useFlag("agent-mode") && serverSessionsOn(ds);
  if (!on) return null;
  return <PastChatsList />;
}

function PastChatsList() {
  const ds = useDataSource();
  const qc = useQueryClient();
  const busy = useSyncExternalStore(subscribeChatBusy, chatBusy, chatBusy);
  const list = useQuery({ queryKey: SESSIONS_KEY, queryFn: () => ds.listSessions() });
  const [editing, setEditing] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [asking, setAsking] = useState<string | null>(null);
  const [unsaved, setUnsaved] = useState<string | null>(null);
  const refresh = () => void qc.invalidateQueries({ queryKey: SESSIONS_KEY });

  useEffect(() => {
    const synced = () => {
      setUnsaved(null);
      void qc.invalidateQueries({ queryKey: SESSIONS_KEY });
    };
    const failed = (e: Event) => setUnsaved((e as CustomEvent<{ message: string }>).detail.message);
    sessionBus.addEventListener(SYNCED_EVENT, synced);
    sessionBus.addEventListener(FAILED_EVENT, failed);
    return () => {
      sessionBus.removeEventListener(SYNCED_EVENT, synced);
      sessionBus.removeEventListener(FAILED_EVENT, failed);
    };
  }, [qc]);

  const open = useMutation({
    mutationFn: (id: string) => ds.getSession(id),
    onSuccess: (doc) => sessionBus.dispatchEvent(new CustomEvent(OPEN_EVENT, { detail: doc })),
  });
  const rename = useMutation({
    mutationFn: (b: { id: string; title: string }) => ds.renameSession(b.id, b.title),
    onSuccess: () => {
      setEditing(null);
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => ds.deleteSession(id),
    onSuccess: (_out, id) => {
      sessionBus.dispatchEvent(new CustomEvent(DELETED_EVENT, { detail: id }));
      setAsking(null);
      refresh();
    },
  });
  const error = list.error ?? open.error ?? rename.error ?? remove.error;

  return (
    <section className="flex flex-col gap-1" aria-label="Past chats">
      <h3 className="text-xs font-medium">Past chats</h3>
      {error && <p role="alert" className="break-words text-xs text-bad">{error instanceof Error ? error.message : String(error)}</p>}
      {unsaved && <p role="status" className="break-words text-xs text-bad">The last answer was not saved to the server: {unsaved}</p>}
      {list.data && list.data.sessions.length === 0 && <p className="text-xs text-muted-foreground">Finished chats are kept here, on this machine.</p>}
      <ul className="flex max-h-72 flex-col gap-1 overflow-y-auto">
        {(list.data?.sessions ?? []).map((s: SessionSummary) => (
          <li key={s.id} className="flex flex-col gap-0.5 rounded-md border p-2 text-sm">
            {editing === s.id ? (
              <form
                className="flex items-center gap-1"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (title.trim()) rename.mutate({ id: s.id, title });
                }}
              >
                <Input value={title} onChange={(e) => setTitle(e.target.value)} aria-label="Chat title" maxLength={120} autoFocus />
                <Button type="submit" variant="ghost" size="sm" aria-label="Save title" disabled={rename.isPending || !title.trim()}><Check aria-hidden /></Button>
                <Button type="button" variant="ghost" size="sm" aria-label="Cancel rename" onClick={() => setEditing(null)}><X aria-hidden /></Button>
              </form>
            ) : (
              <button
                type="button"
                className="flex items-start gap-1.5 text-left font-medium disabled:opacity-60"
                disabled={busy || open.isPending}
                title={busy ? "Wait for the answer to finish" : "Open this chat"}
                onClick={() => open.mutate(s.id)}
              >
                <MessageSquare aria-hidden className="mt-0.5 size-3.5 shrink-0" />
                <span className="line-clamp-2 break-words">{s.title}</span>
              </button>
            )}
            <p className="text-xs text-muted-foreground">
              {when(s.updated)} · {s.turns} turn{s.turns === 1 ? "" : "s"}
              {s.cost_usd ? ` · ${fmtUsd(s.cost_usd)}` : ""}
            </p>
            {s.preview && s.preview !== s.title && <p className="line-clamp-1 break-words text-xs text-muted-foreground">{s.preview}</p>}
            <div className="flex gap-1">
              <Button variant="ghost" size="sm" aria-label={`Rename ${s.title}`} onClick={() => { setEditing(s.id); setTitle(s.title); }}>
                <Pencil aria-hidden />
              </Button>
              {asking === s.id ? (
                <>
                  <Button variant="ghost" size="sm" className="text-bad" disabled={remove.isPending} onClick={() => remove.mutate(s.id)}>Delete chat</Button>
                  <Button variant="ghost" size="sm" onClick={() => setAsking(null)}>Keep</Button>
                </>
              ) : (
                <Button variant="ghost" size="sm" aria-label={`Delete ${s.title}`} onClick={() => setAsking(s.id)}><Trash2 aria-hidden /></Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
