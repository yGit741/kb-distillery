import type { DataSource } from "@/api";
import { createEmbeddedDataSource } from "@/api";

/** A DataSource whose every method rejects unless the test overrides it. */
export function mockDataSource(over: Partial<DataSource> = {}): DataSource {
  return { ...createEmbeddedDataSource(), kind: "http", ...over };
}
