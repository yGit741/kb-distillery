import { CircleHelp, ListFilter, Maximize, Network, Palette, X, ZoomIn, ZoomOut } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { DisplayPanel } from "./DisplayPanel";
import { FiltersPanel } from "./FiltersPanel";
import { LayoutPanel } from "./LayoutPanel";
import { useGraphUi } from "./store";
import { TOOLS, type GraphToolContext } from "./tools";

const HELP: readonly [string, string][] = [
  ["Search everything", "Space"],
  ["Ask an agent", "/ (coming soon)"],
  ["Pan", "scroll, two-finger swipe, or drag the background"],
  ["Zoom", "pinch, Cmd+scroll, + and −"],
  ["Fit to view", "F"],
  ["Labels", "hover a page; a click labels its neighbours"],
  ["Move a page", "drag it"],
  ["Read the page here", "double-click"],
  ["Open in Pages", "E (one selected)"],
  ["Page menu", "right-click a page"],
  ["Select several", "Shift or Cmd/Ctrl+click"],
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
}

const TITLES: Record<string, string> = { filter: "Filters", look: "Display", layout: "Layout and sync", help: "Shortcuts" };

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

/** The one toolbar: panels (filters, display, layout, help), zoom and fit, plus whatever TOOLS registers. */
export function Toolbar({ onFit, onZoom, onReheat, onRefresh, refreshing, stats, toolContext }: Props) {
  const flyout = useGraphUi((s) => s.flyout);
  const hasFilter = useGraphUi((s) => s.search !== "" || s.rules.length > 0);
  const open = useGraphUi((s) => s.openFlyout);
  const close = () => useGraphUi.setState({ flyout: null });
  const activeTool = TOOLS.find((t) => t.id === flyout);
  return (
    <>
      <nav aria-label="Graph tools" className="pointer-events-auto absolute right-3 top-3 z-20 flex flex-col gap-0.5 rounded-lg border bg-card/95 p-0.5 shadow-[var(--shadow)]">
        <IconButton label={hasFilter ? "Filters (active)" : "Filters"} active={flyout === "filter" || hasFilter} onClick={() => open("filter")}>
          <ListFilter aria-hidden />
        </IconButton>
        <IconButton label="Display: labels, colour, size" active={flyout === "look"} onClick={() => open("look")}>
          <Palette aria-hidden />
        </IconButton>
        <IconButton label="Layout and sync" active={flyout === "layout"} onClick={() => open("layout")}>
          <Network aria-hidden />
        </IconButton>
        {TOOLS.map((t) => (
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
      {flyout && (
        <section
          aria-label={activeTool?.label ?? TITLES[flyout] ?? flyout}
          className="pointer-events-auto absolute right-14 top-3 z-20 flex max-h-[calc(100%-1.5rem)] w-[min(20rem,calc(100%-4.5rem))] flex-col rounded-lg border bg-card shadow-[var(--shadow)] max-sm:top-14 max-sm:max-h-[calc(100%-4.5rem)]"
        >
          <header className="flex items-center justify-between border-b px-3 py-1.5">
            <h2 className="text-sm font-semibold">{activeTool?.label ?? TITLES[flyout] ?? flyout}</h2>
            <Button variant="ghost" size="icon" className="size-7" aria-label="Close panel" onClick={close}>
              <X aria-hidden />
            </Button>
          </header>
          <div className="overflow-y-auto p-3">
            {flyout === "filter" && <FiltersPanel />}
            {flyout === "look" && <DisplayPanel />}
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
