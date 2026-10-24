import {
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";
import { IS_SHARE } from "@/share/env";
import { LegacyCard } from "@/features/legacy/LegacyCard";
import { ROUTES, type Route } from "@/routes/registry";
import { SEARCH } from "@/routes/search";
import { AppShell } from "./AppShell";
import { ErrorBoundary } from "@/components/states";

/** The app is served under /app (vite `base`, FastAPI spa router). */
export const BASEPATH = import.meta.env.BASE_URL.replace(/\/$/, "");

const rootRoute = createRootRoute({ component: AppShell });

function screenRoutes(def: Route) {
  const Screen = def.Screen ?? (() => <LegacyCard id={def.id} />);
  const validateSearch = SEARCH[def.id as keyof typeof SEARCH] as (raw: Record<string, unknown>) => Record<string, unknown>;
  const component = () => (
    <ErrorBoundary label={def.label}>
      <Screen />
    </ErrorBoundary>
  );
  return [def.path, ...(def.extraPaths ?? [])].map((path) =>
    createRoute({ getParentRoute: () => rootRoute, path, component, validateSearch }),
  );
}

// A share build has no Home screen: the entry point is the graph.
const shareIndex = IS_SHARE
  ? [createRoute({ getParentRoute: () => rootRoute, path: "/", beforeLoad: () => { throw redirect({ to: "/graph" } as never); } })]
  : [];

const routeTree = rootRoute.addChildren([...shareIndex, ...ROUTES.flatMap(screenRoutes)]);

export function createAppRouter(history?: RouterHistory, basepath: string = BASEPATH) {
  return createRouter({ routeTree, history, basepath: basepath || "/", defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
