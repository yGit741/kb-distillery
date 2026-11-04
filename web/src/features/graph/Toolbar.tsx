import { ArrowLeft, CircleHelp, ListFilter, Maximize, Network, SlidersHorizontal, X, ZoomIn, ZoomOut } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { FiltersPanel } from "./FiltersPanel";
import { LayoutPanel } from "./LayoutPanel";
import { useGraphUi } from "./store";
import { useVisibleTools, type GraphToolContext } from "./tools";

const HELP: readonly [string, string][] = [
  ["Search everything", "Space"],
  ["Ask an agent", "/ (coming soon)"],
  ["Pan", "drag the background, or Shift+scroll"],
  ["Zoom", "scroll or pinch (toward the cursor), + and −"],
  ["Fit to view", "F"],
  ["Labels", "hover a page; a click labels its neighbours"],
  ["Move a page", "drag it"],
  ["Read the page here", "double-click"],
  ["Open in Pages", "E (one selected)"],
  ["Page menu", "right-click a page"],
  ["Select several", "Shift or Cmd/Ctrl+click"],
  ["Box select", "right-drag (Shift adds, Cmd/Ctrl draws a lasso)"],
  ["Clear / close", "Esc, or right-click empty space"],
];

interface Props {
  onFit: () => void;
  onZoom: (factor: number) => void;
  onReheat: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  stats: string;
  toolContext: GraphToolContext;
  /** Set when the graph was opened from Home: a back button heads the bar. */
  onBack?: () => void;
}

const TITLES: Record<string, string> = { filter: "Filters", layout: "Layout and sync", help: "Shortcuts" };

function IconButton({ label, active, onClick, children }: { label: string; active?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <Button
      variant={active ? "secondary" : "ghost"}
      size="icon"
      className={cn("size-9", active && "bg-accent-soft text-primary")}
      aria-label={label}
      title={label}
      aria-pressed={active}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

/** The one toolbar, a slim bar on the left: the labels & views rail, panels (filters, display, layout, help), zoom and fit, plus whatever TOOLS registers. */
export function Toolbar({ onFit, onZoom, onReheat, onRefresh, refreshing, stats, toolContext, onBack }: Props) {
  const flyout = useGraphUi((s) => s.flyout);
  const hasFilter = useGraphUi((s) => s.search !== "" || s.rules.length > 0);
  const openFlyout = useGraphUi((s) => s.openFlyout);
  const open = (id: string) => {
    useGraphUi.setState({ railOpen: false });
    openFlyout(id);
  };
  const close = () => useGraphUi.setState({ flyout: null });
  const tools = useVisibleTools();
  const activeTool = tools.find((t) => t.id === flyout);
  const railOpen = useGraphUi((s) => s.railOpen);
  return (
    <>
      <nav aria-label="Graph tools" className="pointer-events-auto absolute left-3 top-3 z-20 flex flex-col gap-0.5 rounded-lg border bg-card/95 p-0.5 shadow-[var(--shadow)]">
        {onBack && (
          <>
            <IconButton label="Back to Home" onClick={onBack}>
              <ArrowLeft aria-hidden />
            </IconButton>
            <hr className="mx-1 my-0.5" />
          </>
        )}
        <IconButton label="Labels & views" active={railOpen} onClick={() => useGraphUi.setState({ railOpen: !railOpen, flyout: null })}>
          <SlidersHorizontal aria-hidden />
        </IconButton>
        <IconButton label={hasFilter ? "Filters (active)" : "Filters"} active={flyout === "filter" || hasFilter} onClick={() => open("filter")}>
          <ListFilter aria-hidden />
        </IconButton>
        <IconButton label="Layout and sync" active={flyout === "layout"} onClick={() => open("layout")}>
          <Network aria-hidden />
        </IconButton>
        {tools.map((t) => (
          <IconButton key={t.id} label={t.label} active={flyout === t.id} onClick={() => open(t.id)}>
            {t.icon}
          </IconButton>
        ))}
        <hr className="mx-1 my-0.5" />
        <IconButton label="Zoom in (+)" onClick={() => onZoom(1.25)}>
          <ZoomIn aria-hidden />
        </IconButton>
        <IconButton label="Zoom out (−)" onClick={() => onZoom(1 / 1.25)}>
          <ZoomOut aria-hidden />
        </IconButton>
        <IconButton label="Fit to view (F)" onClick={onFit}>
          <Maximize aria-hidden />
        </IconButton>
        <IconButton label="Shortcuts" active={flyout === "help"} onClick={() => open("help")}>
          <CircleHelp aria-hidden />
        </IconButton>
      </nav>
      {flyout && activeTool?.sheet && (
        <section
          aria-label={activeTool.label}
          className="pointer-events-auto absolute bottom-3 right-3 top-3 z-20 flex w-[min(48rem,calc(100%-5rem))] flex-col rounded-lg border bg-card shadow-[var(--shadow)]"
        >
          <header className="flex items-center justify-between border-b px-3 py-1.5">
            <h2 className="text-sm font-semibold">{activeTool.label}</h2>
            <Button variant="ghost" size="icon" className="size-7" aria-label="Close panel" onClick={close}>
              <X aria-hidden />
            </Button>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto">{activeTool.sheet()}</div>
        </section>
      )}
      {flyout && !activeTool?.sheet && (
        <section
          aria-label={activeTool?.label ?? TITLES[flyout] ?? flyout}
          className="pointer-events-auto absolute left-14 top-3 z-20 flex max-h-[calc(100%-5rem)] w-[min(20rem,calc(100%-4.5rem))] flex-col rounded-lg border bg-card shadow-[var(--shadow)] max-sm:top-14 max-sm:max-h-[calc(100%-4.5rem)]"
        >
          <header className="flex items-center justify-between border-b px-3 py-1.5">
            <h2 className="text-sm font-semibold">{activeTool?.label ?? TITLES[flyout] ?? flyout}</h2>
            <Button variant="ghost" size="icon" className="size-7" aria-label="Close panel" onClick={close}>
              <X aria-hidden />
            </Button>
          </header>
          <div className="overflow-y-auto p-3">
            {flyout === "filter" && <FiltersPanel />}
            {flyout === "layout" && <LayoutPanel onReheat={onReheat} onRefresh={onRefresh} refreshing={refreshing} stats={stats} />}
            {flyout === "help" && (
              <table className="w-full text-xs">
                <tbody>
                  {HELP.map(([a, b]) => (
                    <tr key={a} className="border-b last:border-0">
                      <td className="py-1 pr-2 font-medium">{a}</td>
                      <td className="py-1 text-muted-foreground">{b}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {activeTool?.panel?.(toolContext)}
          </div>
        </section>
      )}
    </>
  );
}
