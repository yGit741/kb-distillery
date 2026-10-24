import { useNavigate, useSearch } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Empty, ErrorState, Loading } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useApiQuery } from "@/lib/useApiQuery";
import { useKb } from "@/lib/store";
import type { ScopesSearch } from "@/routes/search";
import { Editor, type EditorInit } from "./Editor";
import { newRows, readDrafts, type ScopeSummary } from "./logic";

type Summary = ScopeSummary;

function ScopeList({ scopes, current, onOpen, onOpenDraft, onNew }: {
  scopes: Summary[];
  current: string | null;
  onOpen: (slug: string) => void;
  onOpenDraft: (key: string) => void;
  onNew: () => void;
}) {
  const known = new Set(scopes.map((s) => s.slug));
  const drafts = Object.entries(readDrafts().drafts).filter(([, d]) => d.isNew && !known.has(d.slug));
  return (
    <aside aria-label="Scopes" className="flex min-w-0 flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-xl font-semibold">Scopes</h1>
        <Button size="sm" onClick={onNew}>
          New scope
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        A scope is a named set of pages the chat agent is limited to. {scopes.length} saved.
      </p>
      <ul className="flex max-h-72 flex-col gap-2 overflow-y-auto lg:max-h-none">
        {drafts.map(([key, d]) => (
          <li key={key}>
            <button type="button" onClick={() => onOpenDraft(key)} className="w-full rounded-lg border border-dashed p-3 text-left hover:bg-accent">
              <span className="block truncate font-medium">{d.title || d.slug}</span>
              <span className="text-xs text-muted-foreground">draft · {d.rows.length} files · unsaved</span>
            </button>
          </li>
        ))}
        {scopes.map((s) => {
          const pct = Math.round(100 * (s.coverage ?? 0));
          return (
            <li key={s.slug}>
              <button
                type="button"
                aria-current={s.slug === current ? "true" : undefined}
                onClick={() => onOpen(s.slug)}
                className={`w-full rounded-lg border p-3 text-left hover:bg-accent ${s.slug === current ? "border-primary bg-accent-soft" : ""}`}
              >
                <span className="block truncate font-medium">{s.title || s.slug}</span>
                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{s.files} files</span>
                  <span className="h-1.5 w-16 overflow-hidden rounded bg-secondary" title={`${pct}% digested`}>
                    <span className="block h-full bg-primary" style={{ width: `${pct}%` }} />
                  </span>
                  <span>{pct}%</span>
                </span>
                {s.updated && <span className="block text-xs text-muted-foreground">{s.updated.slice(0, 10)}</span>}
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}

/** Fetches what the editor starts from (a saved scope, optionally merged with a graph draft rows) and mounts it. */
function Opened({ slug, draftKey, notice, onDirty, onSaved, onDeleted, onDuplicated }: {
  slug: string;
  draftKey: string;
  notice: string;
  onDirty: (d: boolean) => void;
  onSaved: (slug: string, wasNew: boolean, message: string) => void;
  onDeleted: (slug: string) => void;
  onDuplicated: (slug: string) => void;
}) {
  const q = useApiQuery(["scope", slug], (ds) => ds.getScope(slug));
  const draft = draftKey ? readDrafts().drafts[draftKey] : undefined;
  const [init, setInit] = useState<EditorInit | null>(null);
  useEffect(() => {
    if (!q.data || init) return;
    const extra = draft ? newRows(q.data.rows, draft.rows) : [];
    setInit({
      isNew: false,
      slug: q.data.slug,
      title: q.data.title,
      why: q.data.why,
      status: q.data.status,
      rows: [...q.data.rows, ...extra],
      draftKey,
      message: extra.length ? "Unsaved: rows added from the graph are merged in. Press Save to keep them." : notice,
    });
  }, [q.data, init, draft, draftKey, notice]);
  if (q.isError) return <ErrorState title={`Could not open ${slug}`} error={q.error} onRetry={() => void q.refetch()} />;
  if (!init) return <Loading label="Loading scope" rows={4} />;
  return <Editor init={init} projection={q.data?.projection} onDirty={onDirty} onSaved={onSaved} onDeleted={onDeleted} onDuplicated={onDuplicated} />;
}

export function ScopesScreen() {
  const search = useSearch({ strict: false }) as ScopesSearch;
  const navigate = useNavigate();
  const list = useApiQuery(["scopes"], (ds) => ds.listScopes());
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState<(() => void) | null>(null);
  const dirty = useRef(false);
  const onDirty = useCallback((d: boolean) => {
    dirty.current = d;
  }, []);

  const go = (to: ScopesSearch, nowCreating = false, msg = "", force = false) => {
    const run = () => {
      dirty.current = false;
      setCreating(nowCreating);
      setNotice(msg);
      void navigate({ to: "/scopes" as string, search: to as never });
    };
    if (dirty.current && !force) setPending(() => run);
    else run();
  };

  const draftKey = search.draft ?? "";
  const draft = useMemo(() => (draftKey ? readDrafts().drafts[draftKey] : undefined), [draftKey]);
  useEffect(() => {
    useKb.getState().setScopeDraft(draftKey || null);
  }, [draftKey]);

  let body;
  if (search.scope) {
    body = (
      <Opened key={search.scope} slug={search.scope} draftKey="" notice={notice} onDirty={onDirty}
        onSaved={(s, wasNew, m) => { if (wasNew) go({ scope: s }, false, m, true); }}
        onDeleted={(s) => { dirty.current = false; setNotice(`Deleted ${s}.`); void navigate({ to: "/scopes" as string, search: {} as never }); }}
        onDuplicated={(s) => go({ scope: s }, false, `Duplicated as ${s}.`, true)} />
    );
  } else if (draft && !draft.isNew) {
    body = (
      <Opened key={`draft-${draftKey}`} slug={draft.slug} draftKey={draftKey} notice={notice} onDirty={onDirty}
        onSaved={(s, wasNew, m) => { if (wasNew) go({ scope: s }, false, m, true); }}
        onDeleted={() => go({}, false, "", true)} onDuplicated={(s) => go({ scope: s }, false, "", true)} />
    );
  } else if (creating || draftKey) {
    const init: EditorInit = {
      isNew: true,
      slug: draft?.slug ?? "",
      title: draft?.title ?? "",
      why: "",
      status: "",
      rows: draft?.rows ?? [],
      draftKey: draft ? draftKey : "",
      message: draft ? "" : draftKey ? "That draft no longer exists. Add files below, or select nodes on the graph." : "Add files below, or select nodes on the graph and resolve them here.",
    };
    body = (
      <Editor key={`new-${draftKey}`} init={init} onDirty={onDirty}
        onSaved={(s, wasNew, m) => { if (wasNew) go({ scope: s }, false, m, true); }}
        onDeleted={() => go({}, false, "", true)} onDuplicated={(s) => go({ scope: s }, false, "", true)} />
    );
  } else {
    body = <p className="rounded-lg border p-4 text-sm text-muted-foreground">{notice || "Pick a scope on the left, or start a new one. Build one from the graph by selecting nodes, then resolve them here."}</p>;
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-6 px-4 py-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
      {list.isLoading ? (
        <Loading label="Loading scopes" />
      ) : list.isError ? (
        <ErrorState title="Could not load scopes" error={list.error} onRetry={() => void list.refetch()} />
      ) : list.data && list.data.scopes.length === 0 && !creating && !draftKey ? (
        <aside className="flex flex-col gap-2">
          <h1 className="text-xl font-semibold">Scopes</h1>
          <Empty>No scopes yet.</Empty>
          <Button size="sm" onClick={() => go({}, true)}>New scope</Button>
        </aside>
      ) : (
        <ScopeList
          scopes={list.data?.scopes ?? []}
          current={search.scope ?? null}
          onOpen={(s) => go({ scope: s })}
          onOpenDraft={(k) => go({ draft: k })}
          onNew={() => go({}, true)}
        />
      )}
      <section aria-label="Scope editor" className="min-w-0">{body}</section>

      <Dialog open={!!pending} onOpenChange={(o) => !o && setPending(null)}>
        <DialogContent className="p-4">
          <DialogTitle className="font-semibold">Discard unsaved changes?</DialogTitle>
          <DialogDescription className="mt-1 text-sm text-muted-foreground">
            The open scope has edits that were not saved.
          </DialogDescription>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setPending(null)}>Keep editing</Button>
            <Button onClick={() => { const run = pending; setPending(null); run?.(); }}>Discard</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
