import type { FeatureModule } from "./modules";

/** Private site: home, graph, pages and the read-only lifecycle view. */
export const modules = import.meta.glob<FeatureModule>(
  ["../features/home/index.tsx", "../features/graph/index.tsx", "../features/pages/index.tsx", "../features/lifecycle/index.tsx"],
  { eager: true },
);
