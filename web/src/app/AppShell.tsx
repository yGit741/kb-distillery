import { lazy, Suspense } from "react";
import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { routeOffered } from "@/routes/defs";
import { ROUTES } from "@/routes/registry";
import { ShareFooter } from "@/share/ShareFooter";
import { useTheme } from "@/theme/theme";
import { CommandPalette } from "./CommandPalette";
import { SearchOverlay } from "@/features/graph/shell/SearchOverlay";
import { ShareChip } from "./ShareChip";
import { ToursMenu } from "./ToursMenu";
import { KbBadge } from "./KbBadge";
import { inKnowledge, KNOWLEDGE_TABS, SPLIT_TOP, useDataSystemSplit } from "./knowledgeNav";
import { ReadOnlyBanner } from "./ReadOnlyBanner";
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

const NAV_LINK = "shrink-0 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground [&.active]:bg-accent-soft [&.active]:text-primary";

/**
 * Flag ui.data-system-split: four top items. Knowledge is active on Graph, Pages and Think, which
 * get their own tab row under the bar (KnowledgeTabs). Chat lives in the graph's spark panel.
 */
function SplitNav({ pathname }: { pathname: string }) {
  const knowledge = inKnowledge(pathname);
  const top = (id: string) => ROUTES.find((r) => r.id === id && routeOffered(r));
  const item = (id: string) => {
    const r = top(id);
    return r ? (
      <Link key={r.id} to={r.path} activeOptions={{ exact: r.path === "/", includeSearch: false }} className={NAV_LINK}>
        {r.label}
      </Link>
    ) : null;
  };
  return (
    <>
      {item("home")}
      <Link to={"/graph" as "/"} data-status={knowledge ? "active" : undefined} className={cn(NAV_LINK, knowledge && "active")} activeOptions={{ includeSearch: false }}>
        Knowledge
      </Link>
      {SPLIT_TOP.filter((id) => id !== "home").map(item)}
    </>
  );
}

/** Knowledge's tab row (flag ui.data-system-split), under the bar on Graph, Pages and Think, as Ingest and System have theirs. */
function KnowledgeTabs() {
  const offered = (id: string) => ROUTES.some((r) => r.id === id && routeOffered(r));
  return (
    <div className="mb-4 flex gap-1 border-b" role="tablist" aria-label="Knowledge sections">
      {KNOWLEDGE_TABS.filter((t) => offered(t.id)).map((t) => (
        <Link
          key={t.id}
          to={t.path as "/"}
          role="tab"
          activeOptions={{ includeSearch: false }}
          className="-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground [&.active]:border-primary [&.active]:text-foreground"
        >
          {t.label}
        </Link>
      ))}
    </div>
  );
}

/** One top nav, ONE theme toggle, ONE command palette, one share chip. Screens render in <Outlet/>. */
export function AppShell() {
  const { theme, toggle } = useTheme();
  const embed = useEmbed();
  const agentMode = useFlag("agent-mode");
  useFlag("ui.ingest"); // re-render the nav when a runtime flag that adds a tab arrives
  // flag views-panel: on the graph the dark mode switch lives in the pinned panel (Settings); other screens keep it here
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const onGraph = pathname === "/graph";
  // flag ui.data-system-split: the bar is Home, Knowledge (Graph, Pages, Think), Ingest, System
  const split = useDataSystemSplit();
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
          {split ? <SplitNav pathname={pathname} /> : ROUTES.filter((r) => r.nav && routeOffered(r)).map((r) => (
            <Link
              key={r.id}
              to={r.path}
              activeOptions={{ exact: r.path === "/", includeSearch: false }}
              className={NAV_LINK}
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
      {!embed && <ReadOnlyBanner />}
      <main className={embed ? "min-w-0 flex-1" : "mx-auto w-full min-w-0 max-w-6xl flex-1 px-4 py-4"}>
        {split && !embed && inKnowledge(pathname) && <KnowledgeTabs />}
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
