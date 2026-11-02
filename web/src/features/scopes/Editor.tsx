import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ApiError, useDataSource } from "@/api";
import type { ScopeDetail, ScopeRow } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useKb } from "@/lib/store";
import { AppLink } from "./AppLink";
import { Picker } from "./Picker";
import {
  MAX_SHOWN,
  NO_FILTER,
  checkSave,
  dropDraft,
  filterRows,
  isDigested,
  nameOf,
  newRows,
  normSlug,
  snapshot,
  stats,
  type RowFilter,
} from "./logic";

export interface EditorInit {
  isNew: boolean;
  slug: string;
  title: string;
  why: string;
  maturity: string;
  rows: ScopeRow[];
  draftKey: string;
  message?: string;
}

interface Props {
  init: EditorInit;
  projection?: ScopeDetail["projection"];
  onDirty: (dirty: boolean) => void;
  onSaved: (slug: string, wasNew: boolean, message: string) => void;
  onDeleted: (slug: string) => void;
  onDuplicated: (slug: string) => void;
}

type Msg = { kind: "ok" | "err" | ""; text: string };

const sessionHint = (e: unknown, verb: string): string =>
  e instanceof ApiError && e.status === 409
    ? `Another ops session is open or the slug exists: ${e.message}`
    : `${verb} failed: ${e instanceof Error ? e.message : String(e)}`;

const count = (a: unknown[] | undefined): number => (Array.isArray(a) ? a.length : 0);

export function Editor({ init, projection, onDirty, onSaved, onDeleted, onDuplicated }: Props) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const [slugInput, setSlugInput] = useState(init.slug);
  const [title, setTitle] = useState(init.title);
  const [why, setWhy] = useState(init.why);
  const [rows, setRows] = useState<ScopeRow[]>(init.rows);
  const [isNew, setIsNew] = useState(init.isNew);
  const [baseline, setBaseline] = useState(() => (init.isNew ? "" : snapshot(init.title, init.why, init.rows)));
  const [picked, setPicked] = useState<ReadonlySet<string>>(new Set());
  const [filter, setFilter] = useState<RowFilter>(NO_FILTER);
  const [msg, setMsg] = useState<Msg>({ kind: "", text: init.message ?? "" });
  const [dialog, setDialog] = useState<"dup" | "del" | null>(null);
  const [dupSlug, setDupSlug] = useState("");
  const [dupTitle, setDupTitle] = useState("");

  const slug = isNew ? normSlug(slugInput) : init.slug;
  const dirty = snapshot(title, why, rows) !== baseline;
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  const refetchLists = () => qc.invalidateQueries({ queryKey: ["scopes"] });
  const save = useMutation({
    mutationFn: () =>
      ds.saveScope({ slug, title: title.trim(), why, paths: rows.map((r) => r.path), create: isNew }),
    onSuccess: (r) => {
      if (init.draftKey) {
        dropDraft(init.draftKey);
        if (useKb.getState().scopeDraftId === init.draftKey) useKb.getState().setScopeDraft(null);
      }
      const text = `Saved${r.version ? ` as ${r.version}` : ""}${r.sha ? ` (${r.sha.slice(0, 8)})` : ""}.`;
      setBaseline(snapshot(title, why, rows));
      void refetchLists();
      void qc.invalidateQueries({ queryKey: ["scope", slug] });
      if (isNew) {
        setIsNew(false);
        onSaved(slug, true, text);
      } else {
        setMsg({ kind: "ok", text });
        onSaved(slug, false, text);
      }
    },
    onError: (e) => setMsg({ kind: "err", text: sessionHint(e, "Save") }),
  });
  const duplicate = useMutation({
    mutationFn: () => ds.duplicateScope(init.slug, { new_slug: normSlug(dupSlug), title: dupTitle.trim() }),
    onSuccess: (r) => {
      setDialog(null);
      void refetchLists();
      onDuplicated(r.slug);
    },
    onError: (e) => {
      setDialog(null);
      setMsg({ kind: "err", text: sessionHint(e, "Duplicate") });
    },
  });
  const remove = useMutation({
    mutationFn: () => ds.deleteScope(init.slug),
    onSuccess: () => {
      setDialog(null);
      void refetchLists();
      onDeleted(init.slug);
    },
    onError: (e) => {
      setDialog(null);
      setMsg({ kind: "err", text: sessionHint(e, "Delete") });
    },
  });

  function trySave() {
    const c = checkSave(isNew, slugInput, title, why);
    if (c.error) return setMsg({ kind: "err", text: c.error });
    setMsg({ kind: "", text: "Saving…" });
    save.mutate();
  }

  const have = useMemo(() => new Set(rows.map((r) => r.path)), [rows]);
  const shown = useMemo(() => filterRows(rows, filter), [rows, filter]);
  const formats = useMemo(() => [...new Set(rows.map((r) => r.format).filter(Boolean))].sort(), [rows]);
  const collections = useMemo(() => [...new Set(rows.flatMap((r) => r.collection))].sort().slice(0, 12), [rows]);
  const st = stats(rows);
  const allShownPicked = shown.length > 0 && shown.every((r) => picked.has(r.path));

  const toggleSet = (set: ReadonlySet<string>, v: string): Set<string> => {
    const n = new Set(set);
    if (!n.delete(v)) n.add(v);
    return n;
  };
  const removePaths = (paths: string[]) => {
    const gone = new Set(paths);
    setRows((rs) => rs.filter((r) => !gone.has(r.path)));
    setPicked((p) => new Set([...p].filter((x) => !gone.has(x))));
  };
  const chip = (on: boolean, label: string, onClick: () => void) => (
    <Button key={label} variant={on ? "default" : "outline"} size="sm" aria-pressed={on} onClick={onClick}>
      {label}
    </Button>
  );

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">{isNew ? "New scope" : init.title || init.slug}</h2>
        {dirty && <Badge variant="warn">unsaved changes</Badge>}
      </div>

      {isNew ? (
        <label className="flex flex-col gap-1 text-sm">
          <span>
            Slug <span className="text-muted-foreground">(kebab-case, scope- is added)</span>
          </span>
          <Input value={slugInput} onChange={(e) => setSlugInput(e.target.value)} placeholder="scope-my-topic" autoComplete="off" />
        </label>
      ) : (
        <p className="text-sm text-muted-foreground">
          {init.slug}
          {init.maturity ? ` · ${init.maturity}` : ""}
        </p>
      )}
      <label className="flex flex-col gap-1 text-sm">
        Title
        <Input value={title} onChange={(e) => setTitle(e.target.value)} autoComplete="off" />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        <span>
          Why <span className="text-muted-foreground">required; link a topic or question, e.g. [Info theory](theme-info-theory.md)</span>
        </span>
        <textarea
          value={why}
          onChange={(e) => setWhy(e.target.value)}
          rows={3}
          className="w-full rounded-md border bg-transparent px-3 py-2 text-sm"
        />
      </label>

      {projection && (
        <p className="text-sm text-muted-foreground" data-testid="projection">
          Knowledge: {count(projection.hop0)} pages cite these files, {count(projection.hop1)} one hop away,{" "}
          {count(projection.hubs)} collections, {count(projection.themes)} topics · {count(projection.uncovered)} files
          uncovered
        </p>
      )}
      <p className="text-sm font-medium" data-testid="stats">
        {st.files} files · {st.digested} digested · {st.pct}%
      </p>

      <div className="flex flex-wrap items-center gap-2">
        {chip(filter.undigested, "only undigested", () => setFilter((f) => ({ ...f, undigested: !f.undigested })))}
        {formats.map((f) =>
          chip(filter.formats.has(f), f, () => setFilter((x) => ({ ...x, formats: toggleSet(x.formats, f) }))),
        )}
        {collections.map((c) =>
          chip(filter.collections.has(c), c, () => setFilter((x) => ({ ...x, collections: toggleSet(x.collections, c) }))),
        )}
        <Input
          aria-label="Filter rows"
          placeholder="Filter rows…"
          value={filter.text}
          onChange={(e) => setFilter((f) => ({ ...f, text: e.target.value }))}
          className="min-w-0 basis-40 flex-1"
        />
        <Button variant="outline" size="sm" disabled={!picked.size} onClick={() => removePaths([...picked])}>
          Remove selected ({picked.size})
        </Button>
      </div>

      {rows.length ? (
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="bg-secondary text-left text-xs text-muted-foreground">
              <tr>
                <th className="w-8 p-2">
                  <input
                    type="checkbox"
                    aria-label="Select all shown"
                    checked={allShownPicked}
                    onChange={(e) =>
                      setPicked((p) => {
                        const n = new Set(p);
                        for (const r of shown) e.target.checked ? n.add(r.path) : n.delete(r.path);
                        return n;
                      })
                    }
                  />
                </th>
                <th className="p-2">File</th>
                <th className="p-2">Format</th>
                <th className="p-2">State</th>
                <th className="p-2">Page</th>
                <th className="p-2">Collection</th>
                <th className="w-8 p-2" />
              </tr>
            </thead>
            <tbody>
              {shown.slice(0, MAX_SHOWN).map((r) => (
                <tr key={r.path} className="border-t">
                  <td className="p-2">
                    <input
                      type="checkbox"
                      aria-label={`Select ${nameOf(r.path)}`}
                      checked={picked.has(r.path)}
                      onChange={() => setPicked((p) => toggleSet(p, r.path))}
                    />
                  </td>
                  <td className="max-w-64 truncate p-2" title={r.path}>
                    {nameOf(r.path)}
                  </td>
                  <td className="p-2">{r.format}</td>
                  <td className="p-2">
                    <Badge variant={isDigested(r) ? "ok" : r.disposition === "queued" ? "warn" : "default"}>
                      {r.digestion || r.disposition}
                    </Badge>
                  </td>
                  <td className="p-2">
                    {r.slug && (
                      <AppLink to="/graph" search={{ focus: r.slug }} className="text-primary hover:underline">
                        {r.slug}
                      </AppLink>
                    )}
                  </td>
                  <td className="p-2 text-muted-foreground">{r.collection.join(", ")}</td>
                  <td className="p-2">
                    <Button variant="ghost" size="icon" className="size-7" aria-label={`Remove ${nameOf(r.path)}`} onClick={() => removePaths([r.path])}>
                      ×
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {shown.length > MAX_SHOWN && <p className="p-2 text-sm text-muted-foreground">Showing the first {MAX_SHOWN} of {shown.length}.</p>}
          {!shown.length && <p className="p-3 text-sm text-muted-foreground">No rows match the filter.</p>}
        </div>
      ) : (
        <p className="rounded-lg border p-3 text-sm text-muted-foreground">
          No files yet. Search below, or select nodes on the graph and resolve them here.
        </p>
      )}

      <Picker
        have={have}
        onAdd={(extra, label) => {
          const fresh = newRows(rows, extra);
          setRows((rs) => [...rs, ...fresh]);
          setMsg({ kind: "", text: `Added ${fresh.length} file${fresh.length === 1 ? "" : "s"} from ${label}. Save to keep them.` });
        }}
      />

      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={trySave} disabled={save.isPending}>
          Save
        </Button>
        {!isNew && (
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setDupSlug(`${init.slug}-copy`);
                setDupTitle(`${title || init.slug} (copy)`);
                setDialog("dup");
              }}
            >
              Duplicate
            </Button>
            <Button variant="outline" className="text-bad" onClick={() => setDialog("del")}>
              Delete
            </Button>
          </>
        )}
        <Button asChild variant="secondary">
          <AppLink to="/chat" search={{ scope: slug || undefined }}>
            Ask in chat
          </AppLink>
        </Button>
        {!isNew && (
          <Button asChild variant="secondary">
            <AppLink to="/graph" search={{ scope: slug }}>
              Open in graph
            </AppLink>
          </Button>
        )}
      </div>
      {msg.text && (
        <p role={msg.kind === "err" ? "alert" : "status"} className={msg.kind === "err" ? "text-sm text-bad" : msg.kind === "ok" ? "text-sm text-ok" : "text-sm text-muted-foreground"}>
          {msg.text}
        </p>
      )}

      <Dialog open={dialog === "del"} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="p-4">
          <DialogTitle className="font-semibold">Delete {init.slug}?</DialogTitle>
          <DialogDescription className="mt-1 text-sm text-muted-foreground">
            This removes the scope page and its file list. The raw files stay. It lands as one undoable knowledge step.
          </DialogDescription>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button className="bg-bad text-white" disabled={remove.isPending} onClick={() => remove.mutate()}>
              Delete scope
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog open={dialog === "dup"} onOpenChange={(o) => !o && setDialog(null)}>
        <DialogContent className="p-4">
          <DialogTitle className="font-semibold">Duplicate {init.slug}</DialogTitle>
          <DialogDescription className="sr-only">Name the copy</DialogDescription>
          <div className="mt-3 flex flex-col gap-2">
            <label className="flex flex-col gap-1 text-sm">
              New slug
              <Input value={dupSlug} onChange={(e) => setDupSlug(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              Title
              <Input value={dupTitle} onChange={(e) => setDupTitle(e.target.value)} />
            </label>
          </div>
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDialog(null)}>
              Cancel
            </Button>
            <Button disabled={!normSlug(dupSlug) || duplicate.isPending} onClick={() => duplicate.mutate()}>
              Duplicate
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
