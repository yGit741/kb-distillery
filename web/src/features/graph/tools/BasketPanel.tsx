import { X } from "lucide-react";
import { useMemo, useState } from "react";
import { useDataSource } from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { nameOf, stats } from "@/features/scopes/logic";
import { useApiQuery } from "@/lib/useApiQuery";
import { activeDraft, byFormat, newTarget, useBasket, type BasketTarget } from "../basket";
import { useToolHost } from "../hostContext";
import { pageIds } from "../selection";
import { useGraphUi } from "../store";
import type { GraphToolContext } from ".";

const NEW = "";

/**
 * The basket is a scope draft kept in the browser: add what the selection stands on (its raw files),
 * look at it grouped by format, and hand it to the Scopes screen with Make scope.
 */
export function BasketPanel({ ctx }: { ctx: GraphToolContext }) {
  const ds = useDataSource();
  const host = useToolHost();
  const store = useBasket((s) => s.store);
  const draft = activeDraft(store);
  const scopes = useApiQuery(["scopes"], (d) => d.listScopes());
  const [target, setTarget] = useState(draft && !draft.isNew ? draft.slug : NEW);
  const [title, setTitle] = useState(draft?.isNew ? draft.title : "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const ids = useMemo(() => pageIds(ctx.selection, ctx.byId), [ctx.selection, ctx.byId]);
  const rows = draft?.rows ?? [];
  const st = stats(rows);

  const resolveTarget = (): BasketTarget | null => {
    if (target !== NEW) {
      const s = scopes.data?.scopes.find((x) => x.slug === target);
      return { slug: target, title: s?.title || target, isNew: false };
    }
    return newTarget(title);
  };

  const add = async () => {
    const t = resolveTarget();
    if (!t) {
      setNote("Name the new scope first.");
      return;
    }
    setBusy(true);
    try {
      const res = await ds.resolveScope({ nodes: ids });
      const out = useBasket.getState().add(t, res.rows);
      setNote(`${t.title}: ${out.added} new file${out.added === 1 ? "" : "s"} (${res.rows.length} found under the selection).`);
    } catch (e) {
      setNote(`Could not resolve the selection: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3 text-sm">
      <div className="flex flex-col gap-1.5">
        <label className="flex items-center gap-2 text-xs">
          <span className="w-12 shrink-0 text-muted-foreground">Add to</span>
          <select className="h-8 min-w-0 flex-1 rounded-md border bg-background px-2 text-sm" value={target} onChange={(e) => setTarget(e.target.value)}>
            <option value={NEW}>A new scope…</option>
            {(scopes.data?.scopes ?? []).map((s) => (
              <option key={s.slug} value={s.slug}>
                {s.title || s.slug} ({s.files} files)
              </option>
            ))}
          </select>
        </label>
        {target === NEW && <Input aria-label="Scope name" placeholder="Scope name" value={title} onChange={(e) => setTitle(e.target.value)} autoComplete="off" />}
        <Button size="sm" disabled={!ids.length || busy} onClick={() => void add()}>
          Add the raw files of {ids.length} selected page{ids.length === 1 ? "" : "s"}
        </Button>
        {note && (
          <p className="text-xs text-muted-foreground" role="status">
            {note}
          </p>
        )}
      </div>

      <section aria-label="Draft files" className="border-t pt-2">
        {draft ? (
          <>
            <p className="flex flex-wrap items-baseline gap-x-2">
              <b className="min-w-0 truncate" title={draft.title}>
                {draft.title}
              </b>
              <span className="text-xs text-muted-foreground">
                {draft.isNew ? "unsaved · " : "files to add · "}
                {st.files} files · {st.digested} digested · {st.pct}%
              </span>
            </p>
            <div className="mt-1 max-h-64 overflow-y-auto">
              {rows.length === 0 && <p className="text-xs text-muted-foreground">Empty: select pages, then add their raw files.</p>}
              {byFormat(rows).map(([format, list]) => (
                <details key={format} open className="mb-1">
                  <summary className="cursor-pointer text-xs font-medium">
                    {format} <span className="text-muted-foreground">{list.length}</span>
                  </summary>
                  <ul>
                    {list.map((r) => (
                      <li key={r.path} className="flex items-center gap-1.5 py-0.5 text-xs">
                        <span className="shrink-0 rounded bg-muted px-1 text-[10px] text-muted-foreground">{r.disposition}</span>
                        <span className="min-w-0 flex-1 truncate" title={nameOf(r.path)}>
                          {nameOf(r.path)}
                        </span>
                        {r.slug && ctx.byId.has(r.slug) && (
                          <button type="button" className="shrink-0 text-primary hover:underline" onClick={() => ctx.focus(r.slug as string)}>
                            {r.slug.length > 18 ? `${r.slug.slice(0, 17)}…` : r.slug}
                          </button>
                        )}
                        <button type="button" className="rounded p-0.5 text-muted-foreground hover:bg-accent" aria-label={`Remove ${nameOf(r.path)}`} onClick={() => useBasket.getState().remove(r.path)}>
                          <X className="size-3" aria-hidden />
                        </button>
                      </li>
                    ))}
                  </ul>
                </details>
              ))}
            </div>
            <div className="mt-2 flex gap-1.5">
              <Button
                size="sm"
                disabled={!rows.length}
                onClick={() => {
                  useGraphUi.setState({ flyout: null });
                  host.go("/scopes", { draft: store.active });
                }}
              >
                Make scope
              </Button>
              <Button size="sm" variant="ghost" onClick={() => useBasket.getState().discard()}>
                Discard draft
              </Button>
            </div>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">No draft yet. Select pages, then add their raw files; Make scope opens the draft in Scopes.</p>
        )}
      </section>
    </div>
  );
}
