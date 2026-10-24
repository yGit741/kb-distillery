import type { FeatureModule } from "./modules";

/** Private site: graph, pages and the read-only lifecycle view, plus the snapshot admin panel. */
export const modules = import.meta.glob<FeatureModule>(
  ["../features/graph/index.tsx", "../features/pages/index.tsx", "../features/lifecycle/index.tsx", "../features/share/index.tsx"],
  { eager: true },
);
