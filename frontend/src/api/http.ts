import { ApiError, type DataSource } from "./datasource";
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
  return {
    kind: "http",
    getGraphNodes: async () => (await get<{ nodes: GraphNode[] }>("/graph")).nodes,
    getLifecycle: () => get<LifecycleSnapshot>("/lifecycle"),
    getShareStatus: () => get<ShareStatus>("/share/status"),
  };
}
