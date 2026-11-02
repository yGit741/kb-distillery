import type { ComponentType } from "react";

export interface FeatureModule {
  default: ComponentType;
}

/**
 * Every screen folder, by convention. Share builds swap this file (vite alias, see vite.config.ts) for
 * modules.share-public.ts / modules.share-private.ts, which list their screens literally: a screen that
 * is not imported is not in the bundle at all, it is not merely hidden.
 */
export const modules = import.meta.glob<FeatureModule>("../features/*/index.tsx", { eager: true });
