import { useNavigate } from "@tanstack/react-router";
import { Feather, MessageSquare } from "lucide-react";
import { flag } from "@/flags";
import { useChatDock } from "@/features/graph/tools/chatDockStore";
import { useApiQuery } from "@/lib/useApiQuery";
import { GRAPH_KEY } from "@/lib/query";
import { SYSTEM_TABS } from "@/routes/search";
import { useEffect } from "react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useFlag } from "@/flags/useFlag";
import { routeOffered } from "@/routes/defs";
import { ROUTES, movedTarget } from "@/routes/registry";
import { IS_SHARE } from "@/share/env";
import { useUi } from "./ui-store";

/** The ONE ⌘K palette, mounted once in AppShell. Screens add commands by extending this list later. */
export function CommandPalette() {
  const { paletteOpen, setPaletteOpen } = useUi();
  useFlag("research-tools"); // re-render when the flag lands: it decides whether Covector is listed
  const navigate = useNavigate();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // flag graph-intent: the search line (SearchOverlay) owns Cmd/Ctrl+K on every screen
      if (flag("graph-intent")) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(!useUi.getState().paletteOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPaletteOpen]);

  const go = (to: string) => {
    setPaletteOpen(false);
    void navigate({ to });
  };
  const goSearch = (to: string, search: Record<string, string>) => {
    setPaletteOpen(false);
    void navigate({ to: to as "/", search: search as never });
  };
  // pages come from the graph snapshot, fetched only once the palette is opened (and cached with the graph)
  const graph = useApiQuery([...GRAPH_KEY], (d) => d.getGraph(), { enabled: paletteOpen });
  const pages = graph.data?.nodes ?? [];

  return (
    <CommandDialog open={paletteOpen} onOpenChange={setPaletteOpen} title="Command palette">
      <CommandInput placeholder="Go to… · a page · an action" />
      <CommandList>
        <CommandEmpty>No matching command.</CommandEmpty>
        <CommandGroup heading="Go to">
          {ROUTES.filter((r) => routeOffered(r) && !movedTarget(r)).map((r) => (
            <CommandItem key={r.id} value={`${r.label} ${r.blurb}`} onSelect={() => go(r.path)}>
              <span className="font-medium">{r.label}</span>
              <span className="truncate text-xs text-muted-foreground">{r.blurb}</span>
            </CommandItem>
          ))}
        </CommandGroup>
        <CommandGroup heading="Actions">
          {!IS_SHARE && flag("screen.think") && (
            <CommandItem
              value="quick thought capture think note"
              onSelect={() => {
                setPaletteOpen(false);
                useUi.getState().setCaptureOpen(true);
              }}
            >
              <Feather aria-hidden />
              <span>Quick thought</span>
              <span className="text-xs text-muted-foreground">to think/inbox.md · ⌘⇧Space anywhere</span>
            </CommandItem>
          )}
          {!IS_SHARE && (
            <CommandItem
              value="ask the vault chat agent question"
              onSelect={() => {
                go("/graph");
                useChatDock.getState().set({ open: true });
              }}
            >
              <MessageSquare aria-hidden />
              <span>Ask the vault</span>
              <span className="text-xs text-muted-foreground">chat next to the graph · or “/” in the graph search</span>
            </CommandItem>
          )}
          {!IS_SHARE &&
            SYSTEM_TABS.map((t) => (
              <CommandItem key={t} value={`system ${t}`} onSelect={() => goSearch("/system", t === "overview" ? {} : { tab: t })}>
                <span>System · {t[0]?.toUpperCase() + t.slice(1)}</span>
              </CommandItem>
            ))}
        </CommandGroup>
        {pages.length > 0 && (
          <CommandGroup heading="Pages">
            {pages.map((n) => (
              <CommandItem key={n.id} value={`page ${n.title} ${n.id}`} onSelect={() => goSearch("/graph", { select: n.id, focus: n.id })}>
                <span className="truncate">{n.title || n.id}</span>
                <span className="shrink-0 text-xs text-muted-foreground">{n.type}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
