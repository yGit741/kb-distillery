import { createContext, createElement, useContext, type ReactNode } from "react";
import type { DataSource } from "./datasource";
import { createEmbeddedDataSource } from "./embedded";
import { createHttpDataSource } from "./http";

export * from "./datasource";
export * from "./types";
export * from "./model";
export { createHttpDataSource, createEmbeddedDataSource };

/** `embedded` only when a share build bakes its blob into the page; otherwise the live backend. */
export function defaultDataSource(): DataSource {
  return (globalThis as { KB_EMBEDDED?: unknown }).KB_EMBEDDED ? createEmbeddedDataSource() : createHttpDataSource();
}

const Ctx = createContext<DataSource | null>(null);

export function DataSourceProvider({ source, children }: { source: DataSource; children: ReactNode }) {
  return createElement(Ctx.Provider, { value: source }, children);
}

export function useDataSource(): DataSource {
  const ds = useContext(Ctx);
  if (!ds) throw new Error("useDataSource outside DataSourceProvider");
  return ds;
}
