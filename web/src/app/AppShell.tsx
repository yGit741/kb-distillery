import { lazy, Suspense } from "react";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ROUTES } from "@/routes/registry";
import { ShareFooter } from "@/share/ShareFooter";
import { useTheme } from "@/theme/theme";
import { CommandPalette } from "./CommandPalette";
import { SearchOverlay } from "@/features/graph/shell/SearchOverlay";
import { ShareChip } from "./ShareChip";
import { ToursMenu } from "./ToursMenu";
import { KbBadge } from "./KbBadge";
import { useEmbed } from "./embed";
import { useHeaderFolded } from "./headerFold";
import { HEADER_SLOT_ID } from "./headerSlot";
import { useDataSource } from "@/api";
import { flag } from "@/flags";
import { useFlag } from "@/flags/useFlag";
import { IS_SHARE } from "@/share/env";

// Quick capture ships with the think feature; the lazy import keeps it out of builds where the flag is off.
const QuickCapture = lazy(() => import("@/features/think/QuickCapture"));
// The Cmd-J quick ask (flag `agent-mode`) is lazy for the same reason.
const QuickAsk = lazy(() => import("@/features/chat/QuickAsk"));

/** One top nav, ONE theme toggle, ONE command palette, one share chip. Screens render in <Outlet/>. */
export function AppShell() {
  const { theme, toggle } = useTheme();
  const embed = useEmbed();
  const agentMode = useFlag("agent-mode");
  // flag views-panel: on the graph the dark mode switch lives in the pinned panel (Settings); other screens keep it here
  const onGraph = useRouterState({ select: (s) => s.location.pathname }) === "/graph";
  // the panel only renders its switch with a server behind it (as Corners does): share and static builds keep the header one
  const panelHasSwitch = useDataSource().kind === "http" && !IS_SHARE;
  const themeInPanel = useFlag("views-panel") && useFlag("graph-shell") && onGraph && panelHasSwitch;
  // flag header-fold: on the graph the bar folds away above the screen (the graph's chevron brings it back)
  const folded = useHeaderFolded();
  return (
    <div className="flex min-h-screen flex-col">
      {!embed && (
      <header
        aria-hidden={folded || undefined}
        inert={folded}
        data-folded={folded || undefined}
        className={cn("sticky top-0 z-40 flex h-12 items-center gap-2 border-b bg-card px-4 transition-transform duration-200 motion-reduce:transition-none", folded && "-translate-y-full")}
      >
        <KbBadge />
        <nav aria-label="Main" className="flex min-w-0 shrink items-center gap-1 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {ROUTES.filter((r) => r.nav).map((r) => (
            <Link
              key={r.id}
              to={r.path}
              activeOptions={{ exact: r.path === "/", includeSearch: false }}
              className="shrink-0 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground [&.active]:bg-accent-soft [&.active]:text-primary"
            >
              {r.label}
            </Link>
          ))}
        </nav>
        <div id={HEADER_SLOT_ID} className="min-w-0 flex-1 px-2" />
        <ShareChip />
        <ToursMenu />
        {!themeInPanel && (
          <Button
            variant="ghost"
            size="icon"
            onClick={toggle}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
          </Button>
        )}
      </header>
      )}
      <main className={embed ? "min-w-0 flex-1" : "mx-auto w-full min-w-0 max-w-6xl flex-1 px-4 py-4"}>
        <Outlet />
      </main>
      <ShareFooter />
      <CommandPalette />
      <SearchOverlay />
      {agentMode && (
        <Suspense fallback={null}>
          <QuickAsk />
        </Suspense>
      )}
      {flag("screen.think") && (
        <Suspense fallback={null}>
          <QuickCapture />
        </Suspense>
      )}
    </div>
  );
}
