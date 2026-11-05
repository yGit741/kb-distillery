import {
  Boxes,
  Database,
  FileText,
  GitFork,
  Layers,
  MessageSquare,
  Moon,
  MousePointerSquareDashed,
  Route,
  Send,
  SlidersHorizontal,
  Sparkles,
  Sun,
  TextSearch,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { useUi } from "@/app/ui-store";
import { flag } from "@/flags";
import { useApiQuery } from "@/lib/useApiQuery";
import { cn } from "@/lib/utils";
import { listTours, runTour } from "@/features/tour/tours";
import { useTheme } from "@/theme/theme";
import type { ToolHost } from "../../hostContext";
import { useLayer } from "../../layerStore";
import { useGraphUi } from "../../store";
import { useVisibleTools } from "../../tools";
import type { GNode } from "../../types";
import { ago, chatWhen, type SessionRow } from "./api";
import type { ViewCard } from "./panelModel";

export const PANEL_WIDTH = 300;

const RING =
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";
const ROW = cn(
  "flex min-h-7 w-full items-center gap-2 rounded-lg px-2 text-left text-[12.5px] text-foreground hover:bg-foreground/[0.06] disabled:opacity-50 disabled:hover:bg-transparent",
  RING,
);
const ICON = {
  className: "size-3.5 flex-none text-muted-foreground",
  strokeWidth: 1.6,
  "aria-hidden": true,
} as const;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="px-2 pb-2 pt-1">
      <h3 className="px-2 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
        {title}
      </h3>
      {children}
    </section>
  );
}

const Meta = ({ children }: { children: ReactNode }) => (
  <small className="ml-auto flex-none pl-2 text-[11px] font-normal text-muted-foreground">
    {children}
  </small>
);

export interface ViewsPanelProps {
  views: readonly ViewCard[];
  /** the named view on screen, to mark its card */
  story: string;
  sources: readonly GNode[];
  chats: readonly SessionRow[];
  /** a selected paper page (the one citation genealogy opens on), if any */
  paper: string | null;
  host: ToolHost;
  onView: (card: ViewCard) => void;
  onChat: (row: SessionRow) => void;
  /** closes the corner panels once a command ran */
  done: () => void;
}

/**
 * Flag `views-panel`: the pinned corner's top part, above the pinned list. Four small sections in one calm card,
 * scrolling inside itself: VIEW (saved views with their page counts), SOURCES AND CHATS (the last few), COMMANDS
 * (the graph's tools) and SETTINGS (layout, knowledge base, publisher, tours and the dark mode switch).
 */
export function ViewsPanel({
  views,
  story,
  sources,
  chats,
  paper,
  host,
  onView,
  onChat,
  done,
}: ViewsPanelProps) {
  const tools = useVisibleTools();
  const tool = (id: string) => tools.find((t) => t.id === id);
  const theme = useTheme((s) => s.theme);
  const toggleTheme = useTheme((s) => s.toggle);
  const kb = useApiQuery(["kb"], (d) => d.getKb(), {
    staleTime: Infinity,
    retry: false,
  });
  const [toursOpen, setToursOpen] = useState(false);

  const openPanel = (id: string) => {
    useGraphUi.setState({ railOpen: false, flyout: id });
    done();
  };
  const go = (to: string, search?: Record<string, string>) => {
    host.go(to, search);
    done();
  };

  const commands: {
    key: string;
    label: string;
    icon: ReactNode;
    kbd?: string;
    hint?: string;
    disabled?: boolean;
    run: () => void;
  }[] = [];
  const addTool = (id: string, label: string, icon: ReactNode, kbd?: string) =>
    tool(id) &&
    commands.push({ key: id, label, icon, kbd, run: () => openPanel(id) });
  addTool(
    "selection",
    "Select an area",
    <MousePointerSquareDashed {...ICON} />,
    "S",
  );
  addTool("scopes", "Collections", <Layers {...ICON} />);
  addTool("raw", "Raw files", <Boxes {...ICON} />, "R");
  addTool("query", "Graph query", <TextSearch {...ICON} />);
  commands.push({
    key: "genealogy",
    label: "Citation genealogy",
    icon: <GitFork {...ICON} />,
    hint: paper ? undefined : "select a paper",
    disabled: !paper,
    run: () => {
      if (!paper) return;
      useLayer.getState().openDrawer({ kind: "genealogy", focus: paper });
      done();
    },
  });
  commands.push({
    key: "ask",
    label: "Ask the agent",
    icon: <Sparkles {...ICON} />,
    kbd: "Cmd J",
    run: () => {
      if (flag("agent-mode")) useUi.getState().setAskOpen(true);
      else host.go("/chat");
      done();
    },
  });

  const tours = toursOpen ? listTours().filter((t) => t.summary) : [];

  return (
    <div
      data-testid="views-panel"
      className="pointer-events-auto flex max-h-full min-h-0 flex-col overflow-y-auto overscroll-contain rounded-2xl border bg-card shadow-[var(--shadow)] [scrollbar-width:thin]"
      style={{ width: PANEL_WIDTH }}
    >
      <Section title="View">
        {views.map((v) => (
          <button
            key={v.id}
            type="button"
            aria-pressed={story === v.id}
            onClick={() => onView(v)}
            className={cn(
              ROW,
              story === v.id && "bg-primary/10 font-medium text-primary",
            )}
          >
            <span className="truncate">{v.name}</span>
            <Meta>{v.count}</Meta>
          </button>
        ))}
        {!views.length && (
          <p className="px-2 py-1 text-[12px] text-muted-foreground">
            No views fit this knowledge base yet
          </p>
        )}
      </Section>

      <Section title="Sources and chats">
        {sources.map((n) => (
          <button
            key={n.id}
            type="button"
            title={n.label}
            onClick={() => (
              host.openPage(n.id.replace(/^[^:]+:/, ""), n.kb ?? undefined),
              done()
            )}
            className={ROW}
          >
            <FileText {...ICON} />
            <span className="truncate">{n.label}</span>
            <Meta>{n.type}</Meta>
          </button>
        ))}
        {chats.map((c) => (
          <button
            key={c.id}
            type="button"
            title={c.title}
            onClick={() => onChat(c)}
            className={ROW}
          >
            <MessageSquare {...ICON} />
            <span className="truncate">{c.title}</span>
            <Meta>{chatWhen(c) || ago(c.updated)}</Meta>
          </button>
        ))}
        {!sources.length && !chats.length && (
          <p className="px-2 py-1 text-[12px] text-muted-foreground">
            Nothing yet
          </p>
        )}
      </Section>

      <Section title="Commands">
        {commands.map((c) => (
          <button
            key={c.key}
            type="button"
            disabled={c.disabled}
            title={c.disabled ? c.hint : c.label}
            onClick={c.run}
            className={ROW}
          >
            {c.icon}
            <span className="truncate">{c.label}</span>
            {c.kbd ? (
              <kbd className="ml-auto flex-none pl-2 font-sans text-[11px] text-muted-foreground">
                {c.kbd}
              </kbd>
            ) : (
              <Meta>{c.hint}</Meta>
            )}
          </button>
        ))}
      </Section>

      <Section title="Settings">
        <button
          type="button"
          onClick={() => openPanel("layout")}
          className={ROW}
        >
          <SlidersHorizontal {...ICON} />
          <span className="truncate">Layout and display</span>
        </button>
        <button
          type="button"
          onClick={() => go("/system", { tab: "kbs" })}
          className={ROW}
        >
          <Database {...ICON} />
          <span className="truncate">Knowledge base</span>
          <Meta>{kb.data?.id ?? kb.data?.name ?? ""}</Meta>
        </button>
        <button
          type="button"
          onClick={() => go(flag("screen.share") ? "/share" : "/system")}
          className={ROW}
        >
          <Send {...ICON} />
          <span className="truncate">Publisher</span>
        </button>
        <button
          type="button"
          aria-expanded={toursOpen}
          onClick={() => setToursOpen(!toursOpen)}
          className={ROW}
        >
          <Route {...ICON} />
          <span className="truncate">Tours</span>
        </button>
        {toursOpen && (
          <div className="ml-5 border-l pl-1">
            {tours.map((t) => (
              <button
                key={t.name}
                type="button"
                title={t.summary}
                onClick={() => {
                  done();
                  runTour(t.name);
                }}
                className={ROW}
              >
                <span className="truncate">{t.name}</span>
              </button>
            ))}
            {!tours.length && (
              <p className="px-2 py-1 text-[12px] text-muted-foreground">
                No tours yet
              </p>
            )}
          </div>
        )}
        <button
          type="button"
          role="switch"
          aria-checked={theme === "dark"}
          onClick={toggleTheme}
          className={ROW}
        >
          {theme === "dark" ? <Moon {...ICON} /> : <Sun {...ICON} />}
          <span className="truncate">Dark mode</span>
          <Meta>{theme === "dark" ? "on" : "off"}</Meta>
        </button>
      </Section>
    </div>
  );
}
