import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useDataSource } from "@/api";
import { SHARE_PROFILE } from "@/share/env";
import type { ImportAdapter } from "./adapter";
import { createLocalImportAdapter } from "./localAdapter";
import { createSiteImportAdapter, inboxAccess } from "./siteAdapter";

/**
 * The adapter this build imports through, or null where importing is not offered:
 *  - the local app imports at once (localAdapter);
 *  - the private share build queues the bundle in the Worker's inbox (siteAdapter), only for a signed-in owner whose
 *    inbox is set up (inboxAccess: not an owner, or no bucket, hides it);
 *  - a public snapshot has no Worker and never offers it.
 */
export function useImportAdapter(): ImportAdapter | null {
  const ds = useDataSource();
  const site = ds.kind === "embedded" && SHARE_PROFILE === "private";
  const owner = useQuery({ queryKey: ["inbox-owner"], queryFn: () => inboxAccess(), enabled: site, retry: false, staleTime: Infinity });
  return useMemo(() => {
    if (ds.kind === "http") return createLocalImportAdapter(ds);
    return site && owner.data === true ? createSiteImportAdapter() : null;
  }, [ds, site, owner.data]);
}
