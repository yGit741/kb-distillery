import { keepPreviousData } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import type { SearchHit } from "@/api";
import { useApiQuery } from "@/lib/useApiQuery";
import { findPages, textHits } from "../pageSearch";
import type { GNode } from "../types";
import { useCapabilities } from "./capabilities";

export interface PageResult {
  node: GNode;
  snippet?: string;
  related?: boolean;
  /** A title match the server also found in the text or by meaning (one small mark in the row). */
  also?: ("text" | "related")[];
}

/**
 * Live page results for the search panel: the same logic as the Finder (title and slug matches, then full-text
 * hits, then meaning-based "related" hits when the server has them), over the same query cache.
 */
export function usePageResults(nodes: readonly GNode[], byId: ReadonlyMap<string, GNode>, raw: string, enabled: boolean): PageResult[] {
  // a shared site searches the pages it carries, in the browser; nothing by meaning (that is a model call)
  const byMeaning = useCapabilities().serverSearch;
  const q = raw.trim().toLowerCase();
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(q), 150);
    return () => window.clearTimeout(t);
  }, [q]);

  const text = useApiQuery<{ hits: SearchHit[]; related?: SearchHit[] | null }>(["graph-text", debounced], (ds) => ds.search(debounced, 12), {
    enabled: enabled && debounced.length >= 2,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
  });
  const pages = useMemo(() => (enabled ? findPages(nodes, q) : []), [nodes, q, enabled]);
  const texts = useMemo(
    () => (!enabled || debounced !== q ? [] : textHits(text.data?.hits ?? [], byId, pages)),
    [text.data, byId, pages, enabled, debounced, q],
  );
  const related = useMemo(
    () => (!enabled || debounced !== q ? [] : textHits(byMeaning ? (text.data?.related ?? []) : [], byId, [...pages, ...texts.map((h) => byId.get(h.id)!)], 5)),
    [text.data, byId, pages, texts, enabled, debounced, q, byMeaning],
  );
  return useMemo(() => {
    const sure = debounced === q;
    const inText = new Set(sure ? (text.data?.hits ?? []).map((h) => h.id) : []);
    const inRelated = new Set(sure && byMeaning ? (text.data?.related ?? []).map((h) => h.id) : []);
    const out: PageResult[] = pages.map((node) => {
      const also = [...(inText.has(node.id) ? (["text"] as const) : []), ...(inRelated.has(node.id) ? (["related"] as const) : [])];
      return also.length ? { node, also } : { node };
    });
    for (const h of texts) {
      const node = byId.get(h.id);
      if (node) out.push({ node, snippet: h.snippet });
    }
    for (const h of related) {
      const node = byId.get(h.id);
      if (node) out.push({ node, snippet: h.snippet, related: true });
    }
    return out;
  }, [pages, texts, related, byId, text.data, debounced, q, byMeaning]);
}
