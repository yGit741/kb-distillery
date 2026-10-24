import type { DataSource } from "./datasource";

/** Static share build: data baked into a global JSON blob. Not wired yet (Phase 5). */
export function createEmbeddedDataSource(): DataSource {
  const notBuilt = (): never => {
    throw new Error("embedded data source: not built for share yet");
  };
  return {
    kind: "embedded",
    getLifecycle: async () => notBuilt(),
    getShareStatus: async () => notBuilt(),
    getGraphNodes: async () => notBuilt(),
  };
}
