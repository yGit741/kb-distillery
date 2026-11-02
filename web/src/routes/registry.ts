/**
 * The route registry: ONE list drives the top nav, the ⌘K palette and the router.
 *
 * Convention (no edits here to add a screen): a folder `src/features/<route id>/index.tsx` whose
 * default export is the screen component. Route ids and search schemas live in defs.ts / search.ts. In a
 * share build a route without an imported screen does not exist.
 */
import type { ComponentType } from "react";
import { ROUTE_DEFS, type RouteDef } from "./defs";
import { modules, type FeatureModule } from "@/routes/modules";

export type { RouteDef };

const byId = new Map<string, FeatureModule>();
for (const [file, mod] of Object.entries(modules)) {
  const id = /features\/([^/]+)\/index\.tsx$/.exec(file)?.[1];
  if (id) byId.set(id, mod);
}

export interface Route extends RouteDef {
  Screen: ComponentType;
}

/** A share build keeps only the routes whose screen it imported (modules.share-*.ts); the rest do not exist. */
export const ROUTES: readonly Route[] = ROUTE_DEFS.filter((d) => byId.has(d.id)).map((d) => ({
  ...d,
  Screen: byId.get(d.id)!.default,
}));

export const routeById = (id: string): Route | undefined => ROUTES.find((r) => r.id === id);
