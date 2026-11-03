import {
  createRootRoute,
  createRoute,
  createRouter,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";
import { IS_SHARE } from "@/share/env";
import { useFlag } from "@/flags/useFlag";
import { ROUTES, type Route } from "@/routes/registry";
import { SEARCH } from "@/routes/search";
import { AppShell } from "./AppShell";
import { ErrorBoundary } from "@/components/states";

/** The app is served under /app (vite `base`, FastAPI spa router). */
export const BASEPATH = import.meta.env.BASE_URL.replace(/\/$/, "");

const rootRoute = createRootRoute({ component: AppShell });

/** A route behind a runtime flag shows the router's own "Not Found" while the flag is off (same as an unknown path). */
function Gate({ def }: { def: Route }) {
  const on = useFlag(def.runtimeFlag ?? "research-tools");
  return !def.runtimeFlag || on ? <def.Screen /> : <p>Not Found</p>;
}

function screenRoutes(def: Route) {
  const validateSearch = SEARCH[def.id as keyof typeof SEARCH] as (raw: Record<string, unknown>) => Record<string, unknown>;
  const component = () => (
    <ErrorBoundary label={def.label}>
      <Gate def={def} />
    </ErrorBoundary>
  );
  return [def.path, ...(def.extraPaths ?? [])].map((path) =>
    createRoute({ getParentRoute: () => rootRoute, path, component, validateSearch }),
  );
}

// A share build without the Home screen enters at the graph.
const shareIndex = IS_SHARE && !ROUTES.some((r) => r.id === "home")
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
