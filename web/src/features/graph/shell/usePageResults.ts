import { useEffect, useMemo, useState } from "react";
import type { SearchHit } from "@/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { findPages, textHits } from "../pageSearch";
import type { GNode } from "../types";

export interface PageResult {
  node: GNode;
  snippet?: string;
  related?: boolean;
}

/**
 * Live page results for the search panel: the same logic as the Finder (title and slug matches, then full-text
 * hits, then meaning-based "related" hits when the server has them), over the same query cache.
 */
export function usePageResults(nodes: readonly GNode[], byId: ReadonlyMap<string, GNode>, raw: string, enabled: boolean): PageResult[] {
  const q = raw.trim().toLowerCase();
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q), 150);
    return () => window.clearTimeout(t);
  }, [q]);

  const text = useApiQuery<{ hits: SearchHit[]; related?: SearchHit[] | null }>(["graph-text", debounced], (ds) => ds.search(debounced, 12), {
    enabled: enabled && debounced.length >= 2,
    staleTime: 60_000,
  });
  const pages = useMemo(() => (enabled ? findPages(nodes, q) : []), [nodes, q, enabled]);
  const texts = useMemo(
    () => (!enabled || debounced !== q ? [] : textHits(text.data?.hits ?? [], byId, pages)),
    [text.data, byId, pages, enabled, debounced, q],
  );
  const related = useMemo(
    () => (!enabled || debounced !== q ? [] : textHits(text.data?.related ?? [], byId, [...pages, ...texts.map((h) => byId.get(h.id)!)], 5)),
    [text.data, byId, pages, texts, enabled, debounced, q],
  );
  return useMemo(() => {
    const out: PageResult[] = pages.map((node) => ({ node }));
    for (const h of texts) {
      const node = byId.get(h.id);
      if (node) out.push({ node, snippet: h.snippet });
    }
    for (const h of related) {
      const node = byId.get(h.id);
      if (node) out.push({ node, snippet: h.snippet, related: true });
    }
    return out;
  }, [pages, texts, related, byId]);
}
