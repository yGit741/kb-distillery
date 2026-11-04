import { useMemo } from "react";
import { useDataSource } from "@/api";
import { SHARE_PROFILE } from "@/share/env";
import type { ImportAdapter } from "./adapter";
import { createLocalImportAdapter } from "./localAdapter";
import { createSiteImportAdapter } from "./siteAdapter";

/**
 * The adapter this build imports through: the local app imports at once; the private share build queues the bundle in
 * the site's Worker inbox for the owner's Mac. Null where importing is not offered (a public snapshot has no server).
 * The site cannot tell the owner from another allowed viewer, so the Worker's 401/403 is the answer for those.
 */
export function useImportAdapter(): ImportAdapter | null {
  const ds = useDataSource();
  return useMemo(() => {
    if (ds.kind === "http") return createLocalImportAdapter(ds);
    return SHARE_PROFILE === "private" ? createSiteImportAdapter() : null;
  }, [ds]);
}
