import { ApiError, type DataSource } from "./datasource";
import { fromLegacy, type LegacyNode } from "./legacyModel";
import type { GraphNode } from "./model";
import type { LifecycleSnapshot, ShareStatus } from "./types";

export type Fetch = typeof fetch;

/** Live backend: fetch against /api (Vite proxies it to the dashboard in dev). */
export function createHttpDataSource(fetchImpl: Fetch = (...a) => fetch(...a), base = "/api"): DataSource {
  async function get<T>(path: string): Promise<T> {
    let res: Response;
    try {
      res = await fetchImpl(`${base}${path}`, { cache: "no-store", headers: { Accept: "application/json" } });
    } catch (e) {
      throw new ApiError(`Could not reach ${base}${path}: ${e instanceof Error ? e.message : String(e)}`);
    }
    if (!res.ok) throw new ApiError(`${base}${path} answered ${res.status}`, res.status);
    try {
      return (await res.json()) as T;
    } catch {
      throw new ApiError(`${base}${path} did not return JSON`, res.status);
    }
  }
  interface RawGraph {
    nodes: (LegacyNode & { slug: string; title?: string; areas?: string[] })[];
  }
  return {
    kind: "http",
    // Old backend vocabulary is translated here, at the boundary, and nowhere else.
    getGraphNodes: async () => {
      const g = await get<RawGraph>("/graph");
      return g.nodes.flatMap((n): GraphNode[] => {
        const tag = fromLegacy(n);
        if (!tag) return [];
        return [{ slug: n.slug, title: n.title ?? n.slug, status: n.status ?? "", areas: n.areas ?? [], ...tag }];
      });
    },
    getLifecycle: () => get<LifecycleSnapshot>("/lifecycle"),
    getShareStatus: () => get<ShareStatus>("/share/status"),
  };
}
