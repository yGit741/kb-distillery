import { SYSTEM_TABS } from "@/routes/search";
import { routeOffered, ROUTE_DEFS } from "@/routes/defs";
import { formatKbs } from "@/lib/kbSelection";
import { flag } from "@/flags";
import { useUi } from "@/app/ui-store";
import { useGraphUi } from "../store";
import type { ToolHost } from "../hostContext";
import type { GraphTool } from "../tools";

/** The section a command is listed under. */
export type CommandGroup = "View" | "Panels" | "Knowledge bases" | "Go to";

export const GROUP_ORDER: readonly CommandGroup[] = ["View", "Panels", "Knowledge bases", "Go to"];

/** The name of an icon in the panel's small icon set (SearchPanel maps it to a drawing). */
export type CommandIcon = "fit" | "zoom-in" | "zoom-out" | "reheat" | "refresh" | "labels" | "filters" | "layout" | "help" | "tool" | "kb" | "go" | "think";

export interface Command {
  id: string;
  label: string;
  group: CommandGroup;
  icon: CommandIcon;
  /** A short quiet hint at the right (a shortcut, or what it opens). */
  hint?: string;
  /** For tools: the registered tool's own icon. */
  toolIcon?: GraphTool["icon"];
  /** Extra words the filter matches. */
  keywords?: string;
  run: () => void;
}

export interface KbChoice {
  id: string;
  name: string;
  active: boolean;
  error?: string | null;
}

/** What the commands act on: the same handlers the toolbar uses, handed in by GraphScreen. */
export interface CommandCtx {
  onFit: () => void;
  onZoom: (factor: number) => void;
  onReheat: () => void;
  onRefresh: () => void;
  tools: readonly GraphTool[];
  host: ToolHost;
  /** Merge params into the URL (the `kbs` param picks the knowledge bases the graph shows). */
  setParams?: (patch: Record<string, string | undefined>) => void;
  /** Knowledge bases to switch between; empty unless flag kb-view is on in a live app. */
  kbs: readonly KbChoice[];
  /** The share build has no chat, no think capture and no system screens. */
  share: boolean;
  /** Flag calm-graph: the switcher's views (the same cards as the pinned panel), each a `/view` command. */
  views?: readonly { id: string; name: string; run: () => void }[];
}

const openPanel = (id: string) => useGraphUi.setState({ railOpen: false, flyout: id });

/** Everything the toolbar and the command palette offer for the graph, as one flat list (order = display order). */
export function buildCommands(c: CommandCtx): Command[] {
  const out: Command[] = [
    { id: "fit", label: "Fit to view", group: "View", icon: "fit", hint: "F", keywords: "zoom reset centre", run: c.onFit },
    { id: "zoom-in", label: "Zoom in", group: "View", icon: "zoom-in", hint: "+", keywords: "closer bigger", run: () => c.onZoom(1.25) },
    { id: "zoom-out", label: "Zoom out", group: "View", icon: "zoom-out", hint: "-", keywords: "farther smaller", run: () => c.onZoom(1 / 1.25) },
    { id: "reheat", label: "Reheat layout", group: "View", icon: "reheat", keywords: "settle force simulation spread", run: c.onReheat },
    { id: "refresh", label: "Refresh graph", group: "View", icon: "refresh", keywords: "reload update", run: c.onRefresh },
    ...(c.views ?? []).map<Command>((v) => ({ id: `view:${v.id}`, label: `View: ${v.name}`, group: "View", icon: "labels", keywords: "switch show", run: v.run })),
    {
      id: "labels",
      label: "Labels and views",
      group: "Panels",
      icon: "labels",
      keywords: "rail importance stories",
      run: () => useGraphUi.setState((s) => ({ railOpen: !s.railOpen, flyout: null })),
    },
    { id: "filters", label: "Filters", group: "Panels", icon: "filters", keywords: "types depth rules", run: () => openPanel("filter") },
    { id: "layout", label: "Layout and sync", group: "Panels", icon: "layout", keywords: "force live sync", run: () => openPanel("layout") },
    ...c.tools.map<Command>((t) => ({
      id: `tool:${t.id}`,
      label: t.label,
      group: "Panels",
      icon: "tool",
      toolIcon: t.icon,
      hint: t.shortcut ? t.shortcut.toUpperCase() : undefined,
      run: () => openPanel(t.id),
    })),
    { id: "help", label: "Shortcuts", group: "Panels", icon: "help", keywords: "help keys keyboard", run: () => openPanel("help") },
  ];
  for (const k of c.kbs) {
    if (k.error) continue;
    out.push({
      id: `kb:${k.id}`,
      label: `Show ${k.name || k.id} only`,
      group: "Knowledge bases",
      icon: "kb",
      hint: k.active ? "this app" : "view only",
      keywords: "switch knowledge base",
      run: () => c.setParams?.({ kbs: formatKbs([k.id], c.kbs.find((x) => x.active)?.id ?? null) }),
    });
  }
  // the palette's "Go to" list, minus the screen we are on and the ones folded into a System tab
  for (const r of ROUTE_DEFS) {
    if (r.id === "graph" || r.movedTo || !routeOffered(r)) continue;
    out.push({ id: `go:${r.id}`, label: r.label, group: "Go to", icon: "go", hint: r.blurb, run: () => c.host.go(r.path) });
  }
  if (!c.share) {
    if (flag("screen.think")) {
      out.push({ id: "think-capture", label: "Quick thought", group: "Go to", icon: "think", hint: "to the think inbox", run: () => useUi.getState().setCaptureOpen(true) });
    }
    for (const t of SYSTEM_TABS) {
      const name = t === "kbs" ? "Knowledge bases" : t[0]!.toUpperCase() + t.slice(1);
      out.push({
        id: `system:${t}`,
        label: `System: ${name}`,
        group: "Go to",
        icon: "go",
        run: () => c.host.go("/system", t === "overview" ? undefined : { tab: t }),
      });
    }
  }
  return out;
}

/** The commands matching the text after the slash: every word must appear in the label, group or keywords. */
export function filterCommands(all: readonly Command[], text: string): Command[] {
  const words = text.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return [...all];
  return all.filter((c) => {
    const hay = `${c.label} ${c.group} ${c.keywords ?? ""}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}

/** Edit distance between two short strings. */
function levenshtein(a: string, b: string): number {
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const cur = [i];
    for (let j = 1; j <= b.length; j++) cur[j] = Math.min((prev[j] ?? 0) + 1, (cur[j - 1] ?? 0) + 1, (prev[j - 1] ?? 0) + (a[i - 1] === b[j - 1] ? 0 : 1));
    prev = cur;
  }
  return prev[b.length] ?? 0;
}

function sharedPrefix(a: string, b: string): number {
  let n = 0;
  while (n < a.length && n < b.length && a[n] === b[n]) n++;
  return n;
}

/** Up to `limit` commands nearest to the text: most shared word prefixes first, then the smallest edit distance on the label. */
export function closestCommands(all: readonly Command[], text: string, limit = 3): Command[] {
  const t = text.trim().toLowerCase();
  const words = t.split(/\s+/).filter(Boolean);
  const scored = all.map((c) => {
    const label = c.label.toLowerCase();
    const labelWords = label.split(/\s+/);
    const prefixes = words.reduce((n, w) => n + Math.max(0, ...labelWords.map((lw) => (sharedPrefix(w, lw) >= Math.min(2, w.length) ? sharedPrefix(w, lw) : 0))), 0);
    return { c, prefixes, dist: levenshtein(t, label) };
  });
  scored.sort((x, y) => y.prefixes - x.prefixes || x.dist - y.dist);
  return scored.slice(0, limit).map((s) => s.c);
}
