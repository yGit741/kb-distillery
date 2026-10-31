import { useMemo, useState } from "react";
import type { QueryTable } from "@/api";
import { useDataSource } from "@/api";
import { Button } from "@/components/ui/button";
import { useApiQuery } from "@/lib/useApiQuery";
import { Field, textInput } from "../controls";
import type { GNode } from "../types";
import { revealIds } from "./SelectionPanel";
import type { GraphToolContext } from ".";

const EXAMPLE = "MATCH (q:Question) RETURN q.slug, q.title";

/** A query result cell → the page ids it names (a slug, or a list of slugs as shortest-path returns). */
export function cellIds(value: unknown, resolve: (slug: string) => string | undefined): string[] {
  const vals = Array.isArray(value) ? value : [value];
  return vals.flatMap((v) => {
    const id = typeof v === "string" ? resolve(v) : undefined;
    return id ? [id] : [];
  });
}

/** Bare slug → page id: the id itself, or the one `<kb>:<slug>` that ends in it (a canvas of several knowledge bases). */
export function slugResolver(byId: ReadonlyMap<string, GNode>): (slug: string) => string | undefined {
  const bySuffix = new Map<string, string | null>();
  for (const id of byId.keys()) {
    const i = id.indexOf(":");
    if (i < 0) continue;
    const bare = id.slice(i + 1);
    bySuffix.set(bare, bySuffix.has(bare) ? null : id);
  }
  return (slug) => (byId.has(slug) ? slug : bySuffix.get(slug) ?? undefined);
}

const show = (v: unknown): string => (Array.isArray(v) ? v.map(show).join(" → ") : v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v));

/**
 * Read-only graph queries (flag `graph-relations`): a named query or a Cypher query (the supported subset), the
 * result as a table, and the pages it names highlighted on the canvas (selected, so the rest dims).
 */
export function QueryPanel({ ctx }: { ctx: GraphToolContext }) {
  const ds = useDataSource();
  const named = useApiQuery(["graph-queries"], (d) => d.listGraphQueries(), { staleTime: 5 * 60_000 });
  const [name, setName] = useState("");
  const [params, setParams] = useState<Record<string, string>>({});
  const [cypher, setCypher] = useState("");
  const [result, setResult] = useState<QueryTable | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const resolve = useMemo(() => slugResolver(ctx.byId), [ctx.byId]);
  const picked = named.data?.find((q) => q.name === name);
  const ids = useMemo(() => [...new Set((result?.rows ?? []).flatMap((r) => r.flatMap((c) => cellIds(c, resolve))))], [result, resolve]);

  const run = async (call: () => Promise<QueryTable>) => {
    setBusy(true);
    setError("");
    try {
      setResult(await call());
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const highlight = (list: string[]) => {
    if (!list.length) return;
    revealIds(list);
    ctx.select(list);
  };

  return (
    <div className="flex flex-col gap-3 text-sm">
      <Field label="Named query">
        <select
          className={`${textInput} bg-card text-foreground`}
          value={name}
          disabled={!named.data?.length}
          onChange={(e) => {
            setName(e.target.value);
            setParams({});
          }}
        >
          <option value="">{named.isError ? "could not load" : named.data && !named.data.length ? "none for this knowledge base" : "choose…"}</option>
          {named.data?.map((q) => (
            <option key={q.name} value={q.name}>
              {q.name}
            </option>
          ))}
        </select>
      </Field>
      {picked && (
        <form
          className="flex flex-col gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void run(() => ds.runGraphQuery(picked.name, Object.fromEntries(Object.entries(params).filter(([, v]) => v.trim()))));
          }}
        >
          <p className="text-xs text-muted-foreground">{picked.description}</p>
          {picked.params.map((p) => (
            <Field key={p} label={p}>
              <input className={textInput} value={params[p] ?? ""} onChange={(e) => setParams({ ...params, [p]: e.target.value })} />
            </Field>
          ))}
          <Button type="submit" size="sm" variant="outline" className="self-start" disabled={busy} aria-label="Run named query">
            Run
          </Button>
        </form>
      )}
      <form
        className="flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (cypher.trim()) void run(() => ds.runCypher(cypher));
        }}
      >
        <Field label="Cypher (read-only)">
          <textarea
            rows={3}
            spellCheck={false}
            className="w-full rounded-md border bg-transparent px-2 py-1 font-mono text-xs text-foreground placeholder:text-muted-foreground"
            placeholder={EXAMPLE}
            value={cypher}
            onChange={(e) => setCypher(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                if (cypher.trim()) void run(() => ds.runCypher(cypher));
              }
            }}
          />
        </Field>
        <Button type="submit" size="sm" variant="outline" className="self-start" disabled={busy || !cypher.trim()} aria-label="Run Cypher">
          Run
        </Button>
      </form>
      {error && (
        <p className="text-xs text-bad" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="flex flex-col gap-2" role="status" aria-live="polite">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span>
              {result.row_count} row{result.row_count === 1 ? "" : "s"}
              {result.truncated ? " (first 500)" : ""}
            </span>
            {ids.length > 0 && (
              <Button size="sm" variant="outline" onClick={() => highlight(ids)} title="Select these pages on the canvas; the rest dims">
                Highlight {ids.length}
              </Button>
            )}
          </div>
          {result.rows.length > 0 && (
            <div className="max-h-72 overflow-auto rounded-md border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b">
                    {result.columns.map((c) => (
                      <th key={c} className="px-2 py-1 text-left font-medium">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.rows.map((r, i) => (
                    <tr key={i} className="border-b last:border-0">
                      {r.map((c, j) => {
                        const cIds = cellIds(c, resolve);
                        return (
                          <td key={j} className="max-w-[12rem] px-2 py-0.5 align-top">
                            {cIds.length ? (
                              <button type="button" className="min-h-6 break-all text-left text-primary hover:underline" onClick={() => highlight(cIds)}>
                                {show(c)}
                              </button>
                            ) : (
                              <span className="break-all">{show(c)}</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
