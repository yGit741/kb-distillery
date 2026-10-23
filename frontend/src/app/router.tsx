import {
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from "@tanstack/react-router";
import { LegacyCard } from "@/features/legacy/LegacyCard";
import { LifecycleScreen } from "@/features/lifecycle/LifecycleScreen";
import { ROUTES, type RouteDef } from "@/routes/registry";
import { AppShell } from "./AppShell";

const SCREENS: Record<string, () => React.ReactElement> = {
  lifecycle: LifecycleScreen,
};

const rootRoute = createRootRoute({ component: AppShell });

function screenRoute(def: RouteDef) {
  const Screen = SCREENS[def.id];
  return createRoute({
    getParentRoute: () => rootRoute,
    path: def.path,
    component: Screen ?? (() => <LegacyCard route={def} />),
  });
}

const routeTree = rootRoute.addChildren(ROUTES.map(screenRoute));

export function createAppRouter(history?: RouterHistory) {
  return createRouter({ routeTree, history, defaultPreload: "intent" });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
