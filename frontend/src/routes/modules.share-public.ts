import type { FeatureModule } from "./modules";

/** Public snapshots: graph and pages. Nothing else is imported. */
export const modules = import.meta.glob<FeatureModule>(["../features/graph/index.tsx", "../features/pages/index.tsx"], { eager: true });
