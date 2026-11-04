import { useMemo } from "react";
import { useDataSource } from "@/api";
import type { ImportAdapter } from "./adapter";
import { createLocalImportAdapter } from "./localAdapter";

/**
 * The adapter this build imports through, or null where importing is not offered (the share build: its data is baked
 * into the page). A deployed-site adapter that queues to an inbox is chosen here too.
 */
export function useImportAdapter(): ImportAdapter | null {
  const ds = useDataSource();
  return useMemo(() => (ds.kind === "http" ? createLocalImportAdapter(ds) : null), [ds]);
}
