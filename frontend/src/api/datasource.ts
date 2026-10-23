import type { GraphNode } from "./model";
import type { LifecycleSnapshot, ShareStatus } from "./types";

/** Everything a screen may ask for. Screens depend on this interface only, never on fetch or globals. */
export interface DataSource {
  readonly kind: "http" | "embedded";
  getLifecycle(): Promise<LifecycleSnapshot>;
  getShareStatus(): Promise<ShareStatus>;
  /** Vault nodes in new-model words (type / kind / depth). */
  getGraphNodes(): Promise<GraphNode[]>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
