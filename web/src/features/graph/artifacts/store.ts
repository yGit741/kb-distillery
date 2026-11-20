import { create } from "zustand";
import { QUICK_OFF } from "../quickFilters";
import { useGraphUi, type GraphUiState } from "../store";
import type { ArtifactGraph, ArtifactView } from "./types";

/**
 * The artifact layer's switch, shared by the bar, the corners' view loop and the screen. The URL holds where the
 * screen is (`code` = a template view or `evidence`, `in` = the artifact drilled into); this store only holds what
 * the screen registered (the views, how to go somewhere) and the graph settings set aside while artifacts are drawn.
 */
/**
 * What the views of the artifact layer are drawn from, counted once per graph (the "?" on a view's card reads it):
 * how many nodes of each type and links of each kind, the template's words for each kind, where the graph came from.
 */
export interface ArtifactInfo {
  types: Readonly<Record<string, number>>;
  relations: Readonly<Record<string, number>>;
  relationWords: Readonly<Record<string, string>>;
  template?: string;
  project?: string;
  generator?: string;
  repos: number;
  /** pages that cite a fact about an artifact, and the distinct fact ids the pages cite */
  pages: number;
  facts: number;
}

export function artifactInfo(g: ArtifactGraph, pages: number): ArtifactInfo {
  const tally = (keys: readonly string[]) => keys.reduce<Record<string, number>>((m, k) => ((m[k] = (m[k] ?? 0) + 1), m), {});
  return {
    types: tally(g.nodes.map((n) => n.type)),
    relations: tally(g.links.map((l) => l.kind)),
    relationWords: Object.fromEntries(Object.entries(g.relations ?? {}).flatMap(([k, r]) => (r.description ? [[k, r.description]] : []))),
    template: g.template ?? undefined,
    project: g.project ?? undefined,
    generator: g.generator ?? undefined,
    repos: Object.keys(g.repos ?? {}).length,
    pages,
    facts: new Set(Object.values(g.cites ?? {}).flat()).size,
  };
}

interface ArtifactLayerState {
  views: readonly ArtifactView[];
  /** what the views are drawn from (null: no artifact layer) */
  info: ArtifactInfo | null;
  /** some page cites a fact: the Evidence view has something to draw */
  evidence: boolean;
  /** the view on screen, or null (the concept graph) */
  code: string | null;
  /** the screen's way to go: a view (or `evidence`) and the artifact to drill into; null code = back to the concepts */
  go: (code: string | null, at?: string | null) => void;
  register: (views: readonly ArtifactView[], evidence: boolean, code: string | null, go: (code: string | null, at?: string | null) => void, info?: ArtifactInfo | null) => void;
}

export const useArtifactLayer = create<ArtifactLayerState>((set) => ({
  views: [],
  info: null,
  evidence: false,
  code: null,
  go: () => {},
  register: (views, evidence, code, go, info = null) => set({ views, evidence, code, go, info }),
}));

const KEPT = ["shownTypes", "colorBy", "story", "edgeStory", "hiddenKeys", "view", "quick", "predicate", "search", "rules", "revealed", "spotlight", "spotIds", "readerSlug", "detailsOpen"] as const;
type Kept = Pick<GraphUiState, (typeof KEPT)[number]>;
let kept: Kept | null = null;

/** Draw a scene: its types and colouring, nothing of the concept view's filters; the concept settings are set aside once. */
export function enterArtifacts(types: ReadonlySet<string>, colorBy: "area" | "type"): void {
  const ui = useGraphUi.getState();
  if (!kept) kept = Object.fromEntries(KEPT.map((k) => [k, ui[k]])) as Kept;
  useGraphUi.setState({
    shownTypes: new Set(types),
    colorBy,
    story: "",
    edgeStory: "",
    hiddenKeys: new Set(),
    view: null,
    quick: { ...QUICK_OFF },
    predicate: null,
    search: "",
    rules: [],
    revealed: new Set(),
    spotlight: null,
    spotIds: null,
    readerSlug: null,
    detailsOpen: false,
  });
}

/** Back to the concepts: the settings set aside come back as they were. */
export function leaveArtifacts(): void {
  if (!kept) return;
  useGraphUi.setState({ ...kept });
  kept = null;
}

export const inArtifacts = (): boolean => kept !== null;
