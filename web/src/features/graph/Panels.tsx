import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FiltersPanel } from "./FiltersPanel";
import { LayoutPanel } from "./LayoutPanel";
import { useGraphUi } from "./store";
import { useVisibleTools, type GraphToolContext } from "./tools";

/** Gap between a screen edge and the panels, and the band the corner controls keep (shell/corners/geometry.ts: EDGE + BUTTON + a little air). */
export const PANEL_EDGE = 14;
export const PANEL_INSET = 66;
/** The right side keeps one more strip clear: the colour dots sit on that edge. */
const PANEL_SIDE = PANEL_EDGE + 30;

/** Rows of the shortcuts panel: the keys the graph answers to. */
const HELP: readonly [string, string][] = [
  ["Search everything", "Space, or Cmd/Ctrl+K"],
  ["Commands", "/"],
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

const TITLES: Record<string, string> = { filter: "Filters", layout: "Layout and sync", help: "Shortcuts" };

interface Props {
  onReheat: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  stats: string;
  toolContext: GraphToolContext;
}

/**
 * The panel the graph opens beside the canvas for one thing at a time: filters, layout and sync, shortcuts, a
 * registered tool's panel, or a whole screen folded in (Relations, Scopes) as a wide sheet. What opens it is the
 * store's `flyout` (a command in the search line, a tool's key, `?tool=`). It keeps clear of the four corner
 * controls: panels sit below the top corners and above the bottom ones.
 */
export function Panels({ onReheat, onRefresh, refreshing, stats, toolContext }: Props) {
  const flyout = useGraphUi((s) => s.flyout);
  const tools = useVisibleTools();
  const activeTool = tools.find((t) => t.id === flyout);
  const close = () => useGraphUi.setState({ flyout: null });
  // an id nothing answers to (a tool that is off, a stale ?tool=) draws nothing
  if (!flyout || !(activeTool || flyout in TITLES)) return null;
  const title = activeTool?.label ?? TITLES[flyout] ?? flyout;
  const header = (
    <header className="flex items-center justify-between border-b px-3 py-1.5">
      <h2 className="text-sm font-semibold">{title}</h2>
      <Button variant="ghost" size="icon" className="size-7" aria-label="Close panel" onClick={close}>
        <X aria-hidden />
      </Button>
    </header>
  );
  if (activeTool?.sheet) {
    return (
      <section
        aria-label={title}
        className="pointer-events-auto absolute z-20 flex w-[min(48rem,calc(100%-8rem))] flex-col rounded-lg border bg-card shadow-[var(--shadow)]"
        style={{ right: PANEL_SIDE, top: PANEL_INSET, bottom: PANEL_INSET }}
      >
        {header}
        <div className="min-h-0 flex-1 overflow-y-auto">{activeTool.sheet()}</div>
      </section>
    );
  }
  return (
    <section
      aria-label={title}
      className="pointer-events-auto absolute z-20 flex w-[min(20rem,calc(100%-2rem))] flex-col rounded-lg border bg-card shadow-[var(--shadow)]"
      style={{ left: PANEL_EDGE, top: PANEL_INSET, maxHeight: `calc(100% - ${2 * PANEL_INSET}px)` }}
    >
      {header}
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
  );
}
