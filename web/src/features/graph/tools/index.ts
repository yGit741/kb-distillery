import { useSyncExternalStore, type ReactNode } from "react";
import { flag, flagsVersion, subscribeFlags, type FlagName } from "@/flags";
import type { GraphModel, GNode } from "../types";
import { flagOn, useExperiments } from "./experiments";

/**
 * What a graph tool can see and do. Selection tools (box, lasso, path), expanders, the basket, raw
 * piles, the corpus drawer and digest actions are tools: each one is an entry in TOOLS (a button in the
 * toolbar and an optional panel), not a new branch inside the canvas. The core only reads this registry.
 */
export interface GraphToolContext {
  model: GraphModel;
  byId: ReadonlyMap<string, GNode>;
  visible: ReadonlySet<string>;
  /** The selected page ids (the shared `useKb().selection`). */
  selection: ReadonlySet<string>;
  select: (ids: Iterable<string>, opts?: { additive?: boolean }) => void;
  clearSelection: () => void;
  focus: (id: string, zoom?: boolean) => void;
  /** Screen position (viewport px) of a drawn node, or null while it has none. */
  screenOf: (id: string) => { x: number; y: number } | null;
  openReader: (id: string) => void;
}

export interface GraphTool {
  id: string;
  label: string;
  icon: ReactNode;
  /** Single key that toggles the tool (ignored while typing). */
  shortcut?: string;
  /** The panel body shown in the toolbar flyout when the tool is open. */
  panel?: (ctx: GraphToolContext) => ReactNode;
  /** Always-on overlay (a drag rectangle, a basket chip). Must not take pointer events during gestures. */
  overlay?: (ctx: GraphToolContext) => ReactNode;
  /** An experiment id (./experiments): the tool exists only while that experiment is switched on. */
  flag?: string;
  /** A feature flag (meta-defaults/flags.toml, `@/flags`): the tool exists only while that flag is on. */
  featureFlag?: FlagName;
}

/** The next PR appends here; the core ships none. */
export const TOOLS: GraphTool[] = [];

/** Whether `t` exists now: its experiment (if any) is switched on and its feature flag (if any) is on. */
export function toolOn(t: GraphTool, experiments: ReadonlySet<string>): boolean {
  return flagOn(t.flag, experiments) && (!t.featureFlag || flag(t.featureFlag));
}

/** The tools to draw now: every tool that is on (re-renders when an experiment or a flag override changes). */
export function useVisibleTools(): GraphTool[] {
  const on = useExperiments((s) => s.on);
  useSyncExternalStore(subscribeFlags, flagsVersion, flagsVersion);
  return TOOLS.filter((t) => toolOn(t, on));
}

export function registerTool(tool: GraphTool): void {
  const i = TOOLS.findIndex((t) => t.id === tool.id);
  if (i >= 0) TOOLS[i] = tool;
  else TOOLS.push(tool);
}
