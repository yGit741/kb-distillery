import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useDataSource } from "@/api";
import type { TextHit } from "@/api";

export const TEXT_PAUSE_MS = 300;
const MIN_CHARS = 2;
const LIMIT = 24;

/**
 * Tier 2 of the search line (flag graph-intent): the server's full-text hits for the words typed, asked once the typing
 * pauses. A stale request is aborted when the words change. Hits belong to exactly the text on the line: while a newer
 * text waits for its answer the list is empty, never the previous text's rows.
 */
export function useTextHits(raw: string, enabled: boolean): TextHit[] {
  const ds = useDataSource();
  const q = raw.trim();
  const [paused, setPaused] = useState("");
  useEffect(() => {
    if (!enabled) return setPaused("");
    const t = window.setTimeout(() => setPaused(q), TEXT_PAUSE_MS);
    return () => window.clearTimeout(t);
  }, [q, enabled]);
  const on = enabled && ds.kind !== "embedded" && paused.length >= MIN_CHARS && paused === q;
  const res = useQuery({
    queryKey: ["graph-fts", paused],
    queryFn: ({ signal }) => ds.searchText(paused, { limit: LIMIT, signal }),
    enabled: on,
    staleTime: 30_000,
    retry: false,
  });
  return on ? (res.data?.hits ?? []) : [];
}
