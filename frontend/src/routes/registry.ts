/**
 * The route registry: ONE list drives the top nav, the ⌘K palette and the router.
 *
 * Convention (no edits here to add a screen): a folder `src/features/<route id>/index.tsx` whose
 * default export is the screen component. It may also `export const ported = true` once it replaces
 * the legacy page (the palette then stops offering "Open legacy …"). Route ids and search schemas
 * live in defs.ts / search.ts; routes without a folder fall back to a legacy card.
 */
import type { ComponentType } from "react";
import { IS_SHARE } from "@/share/env";
import { ROUTE_DEFS, legacyHref, type RouteDef } from "./defs";
import { modules, type FeatureModule } from "@/routes/modules";

export { legacyHref };
export type { RouteDef };

const byId = new Map<string, FeatureModule>();
for (const [file, mod] of Object.entries(modules)) {
  const id = /features\/([^/]+)\/index\.tsx$/.exec(file)?.[1];
  if (id) byId.set(id, mod);
}

export interface Route extends RouteDef {
  ported: boolean;
  Screen?: ComponentType;
}

/** A share build keeps only the routes whose screen it imported (modules.share-*.ts); the rest do not exist. */
export const ROUTES: readonly Route[] = ROUTE_DEFS.filter((d) => !IS_SHARE || byId.has(d.id)).map((d) => {
  const mod = byId.get(d.id);
  return { ...d, ported: mod?.ported === true, Screen: mod?.default };
});

export const routeById = (id: string): Route | undefined => ROUTES.find((r) => r.id === id);
