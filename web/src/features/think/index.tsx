/**
 * Think screen: the human's slow space, edited in place. A note list on the left, a CodeMirror 6
 * live-preview editor on the right. Saves are debounced, guarded by an optimistic lock (base_mtime),
 * and land on disk only — kb(think) commits them later, exactly like Obsidian edits.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Feather, Plus } from "lucide-react";
import type { ThinkNote } from "@/api/types";
import { useDataSource } from "@/api";
import { Button } from "@/components/ui/button";
import { Empty, ErrorState, Loading } from "@/components/states";
import { useApiQuery } from "@/lib/useApiQuery";
import { useUi } from "@/app/ui-store";
import type { SearchById } from "@/routes/search";
import { Editor } from "./Editor";

const ago = (mtime: number): string => {
  const s = Math.max(0, Date.now() / 1000 - mtime);
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 2) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
};

type SaveState = { kind: "saved" | "saving" | "dirty" } | { kind: "error"; message: string };

export default function ThinkScreen() {
  const { note } = useSearch({ strict: false }) as SearchById["think"];
  const navigate = useNavigate();
  const ds = useDataSource();
  const qc = useQueryClient();
  const setCaptureOpen = useUi((s) => s.setCaptureOpen);

  const list = useApiQuery(["think"], (d) => d.listThink());
  const open = note ?? list.data?.notes[0]?.name;
  // never refetch under the user's cursor — the optimistic lock (base_mtime) catches outside edits
  const noteQ = useApiQuery(["think", open], (d) => d.getThinkNote(open as string), {
    enabled: !!open,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  // slugs for [[ autocomplete, fetched once alongside the graph cache
  const pagesQ = useApiQuery(["pages-index"], (d) => d.listPages(), { staleTime: 5 * 60_000 });
  const slugs = useMemo(() => (pagesQ.data?.pages ?? []).map((p) => String(p.slug)), [pagesQ.data]);
  const slugsRef = useRef(slugs);
  slugsRef.current = slugs;

  const [save, setSave] = useState<SaveState>({ kind: "saved" });
  const [reloadNonce, setReloadNonce] = useState(0);
  const buffer = useRef<{ note: ThinkNote; text: string } | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const seeded = useRef(""); // which note+reload the buffer was seeded from

  const doSave = useCallback(async () => {
    const b = buffer.current;
    if (!b || b.text === b.note.text) return;
    window.clearTimeout(timer.current);
    const sent = b.text;
    setSave({ kind: "saving" });
    try {
      const res = await ds.saveThinkNote(b.note.name, { text: sent, base_mtime: b.note.mtime });
      // the cache now holds the saved text, so going back to this note never shows a stale copy
      qc.setQueryData<ThinkNote>(["think", b.note.name], { name: b.note.name, text: sent, mtime: res.mtime });
      const cur = buffer.current;
      if (cur?.note.name !== b.note.name) return; // the user moved on — never touch another note's buffer
      cur.note = { name: b.note.name, text: sent, mtime: res.mtime };
      // text typed while the save was in flight stays dirty; its timer is already armed
      setSave(cur.text === sent ? { kind: "saved" } : { kind: "dirty" });
      void qc.invalidateQueries({ queryKey: ["think"], exact: true });
    } catch (e) {
      if (buffer.current?.note.name === b.note.name) setSave({ kind: "error", message: (e as Error).message });
    }
  }, [ds, qc]);

  const onChange = useCallback(
    (text: string) => {
      if (buffer.current) buffer.current.text = text;
      setSave({ kind: "dirty" });
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void doSave(), 1200);
    },
    [doSave],
  );

  // the loaded note becomes the edit buffer — once per note (or explicit reload), so a cache
  // update after a save never clobbers text typed while the save was in flight
  const seedKey = noteQ.data ? `${noteQ.data.name}@${reloadNonce}` : "";
  useEffect(() => {
    if (noteQ.data && seeded.current !== seedKey) {
      seeded.current = seedKey;
      buffer.current = { note: noteQ.data, text: noteQ.data.text };
      setSave({ kind: "saved" });
    }
  }, [noteQ.data, seedKey]);
  const reload = useCallback(() => {
    // fetch first, then remount the editor on the fresh text (the nonce is in its key)
    void noteQ.refetch().then(() => setReloadNonce((n) => n + 1));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noteQ.refetch]);
  useEffect(
    () => () => {
      window.clearTimeout(timer.current);
      void doSave();
    },
    [doSave],
  );

  const openNote = (name: string) => {
    void doSave();
    void navigate({ to: "/think" as "/", search: { note: name } as never });
  };

  const newNote = async () => {
    const name = window.prompt("Name of the new note (a .md file in think/):");
    if (!name) return;
    const file = name.endsWith(".md") ? name : `${name}.md`;
    if (list.data?.notes.some((n) => n.name.toLowerCase() === file.toLowerCase())) {
      void navigate({ to: "/think" as "/", search: { note: file } as never });
      return; // it exists — open it, never truncate it
    }
    await doSave(); // flush the current note first
    try {
      await ds.saveThinkNote(file, { text: "", create: true }); // create-only: the server refuses an existing file
    } catch (e) {
      window.alert(`Could not create ${file}: ${(e as Error).message}`);
      return;
    }
    await qc.invalidateQueries({ queryKey: ["think"], exact: true });
    void navigate({ to: "/think" as "/", search: { note: file } as never });
  };

  if (list.isLoading) return <Loading label="Loading think notes" />;
  if (list.isError) return <ErrorState title="Could not read think/" error={list.error} onRetry={() => void list.refetch()} />;
  const notes = list.data?.notes ?? [];

  return (
    <div className="flex flex-col gap-6 md:flex-row">
      <aside className="shrink-0 md:w-56">
        <div className="mb-2 flex items-center justify-between">
          <h1 className="text-sm font-medium">Think</h1>
          <Button variant="ghost" size="sm" onClick={() => void newNote()} aria-label="New note">
            <Plus className="size-4" aria-hidden />
          </Button>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">Yours alone — agents never write here.</p>
        <nav className="space-y-0.5">
          {notes.map((n) => (
            <button
              key={n.name}
              onClick={() => openNote(n.name)}
              className={`block w-full rounded-md px-2 py-1.5 text-left text-sm ${
                n.name === open ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/50"
              }`}
            >
              <span className="block truncate">{n.name.replace(/\.md$/, "")}</span>
              <span className="block text-[11px] opacity-70">{ago(n.mtime)}</span>
            </button>
          ))}
        </nav>
        <Button variant="ghost" size="sm" className="mt-4 w-full justify-start text-muted-foreground" onClick={() => setCaptureOpen(true)}>
          <Feather className="size-4" aria-hidden /> Quick thought <kbd className="ml-auto text-[10px]">⌘⇧␣</kbd>
        </Button>
      </aside>

      <section className="min-w-0 flex-1">
        {notes.length === 0 ? (
          <Empty>
            think/ is empty. <button className="underline" onClick={() => void newNote()}>Start your first note</button> — or press ⌘⇧Space
            anywhere for a quick thought.
          </Empty>
        ) : noteQ.isLoading ? (
          <Loading label="Opening note" />
        ) : noteQ.isError ? (
          <ErrorState title={`Could not open ${open}`} error={noteQ.error} onRetry={() => void noteQ.refetch()} />
        ) : noteQ.data ? (
          <div>
            <div className="mb-3 flex h-6 items-baseline justify-between gap-4">
              <h2 className="truncate text-lg font-medium">{noteQ.data.name.replace(/\.md$/, "")}</h2>
              <span className="shrink-0 text-xs text-muted-foreground" role="status">
                {save.kind === "saved" && "Saved"}
                {save.kind === "dirty" && "Editing · saves itself"}
                {save.kind === "saving" && "Saving…"}
                {save.kind === "error" && <span className="text-bad">{save.message} </span>}
                {save.kind === "error" && (
                  <>
                    <button
                      className="underline"
                      onClick={() => void navigator.clipboard.writeText(buffer.current?.text ?? "")}
                      title="Copy your unsaved text before reloading"
                    >
                      copy my text
                    </button>{" "}
                    <button className="underline" onClick={reload} title="Replace the editor with what is on disk">
                      reload from disk
                    </button>
                  </>
                )}
              </span>
            </div>
            <Editor
              noteKey={`${noteQ.data.name}@${reloadNonce}`}
              initialText={noteQ.data.text}
              onChange={onChange}
              onSave={() => void doSave()}
              slugs={() => slugsRef.current}
            />
          </div>
        ) : null}
      </section>
    </div>
  );
}
