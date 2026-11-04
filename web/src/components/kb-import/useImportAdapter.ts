import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useDataSource } from "@/api";
import { SHARE_PROFILE } from "@/share/env";
import type { ImportAdapter } from "./adapter";
import { createLocalImportAdapter } from "./localAdapter";
import { createSiteImportAdapter, inboxAccess } from "./siteAdapter";

/**
 * The adapter this build imports through: the local app imports at once; the private share build queues the bundle in
 * the site's Worker inbox for the owner's Mac, but only for a signed-in owner of a site whose inbox is set up
 * (`GET /api/inbox/access`: owner and bucket). Null where importing is not offered (a public snapshot has no server).
 */
export function useImportAdapter(): ImportAdapter | null {
  const ds = useDataSource();
  const site = ds.kind === "embedded" && SHARE_PROFILE === "private";
  const access = useQuery({ queryKey: ["inbox-access"], queryFn: () => inboxAccess(), enabled: site, retry: false, staleTime: Infinity });
  return useMemo(() => {
    if (ds.kind === "http") return createLocalImportAdapter(ds);
    return site && access.data === true ? createSiteImportAdapter() : null;
  }, [ds, site, access.data]);
}
