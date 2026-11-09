import { QueryClient } from "@tanstack/react-query";
import { ApiError, type DataSource } from "@/api";

/** Server state defaults. Data stays fresh for 5 minutes and in memory for 30 after its last user, so switching tabs
 *  shows the cached view at once and refetches nothing; a mount refetches only data that has gone stale. Live data
 *  (jobs, polling) overrides `staleTime` per query; mutations invalidate by key. One retry for network/5xx, none for a
 *  definite 4xx answer. */
export const QUERY_STALE_MS = 5 * 60_000;
export const QUERY_GC_MS = 30 * 60_000;

/** The one key of the default graph snapshot (public layer, this kb): the Graph, Home, search and palette all share it. */
export const GRAPH_KEY = ["graph", false, ""] as const;

/** Warm the heavy query a top-level tab needs (the graph), so the first tab switch finds them cached. Failures stay silent. */
export function prefetchHeavy(client: QueryClient, ds: DataSource): void {
  if (ds.kind !== "http") return;
  void client.prefetchQuery({ queryKey: GRAPH_KEY, queryFn: () => ds.getGraph() });
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: QUERY_STALE_MS,
        gcTime: QUERY_GC_MS,
        refetchOnMount: true, // true = only when stale
        refetchOnWindowFocus: false,
        retry: (count, err) => count < 1 && !(err instanceof ApiError && err.status !== undefined && err.status < 500),
      },
    },
  });
}
