import type { FeatureModule } from "./modules";

/** Public snapshots: home, graph and pages. Nothing else is imported. */
export const modules = import.meta.glob<FeatureModule>(["../features/home/index.tsx", "../features/graph/index.tsx", "../features/pages/index.tsx"], { eager: true });
