import { Layers, Pin } from "lucide-react";
import type { PinnedView } from "@/api";
import { NodeSwatch } from "../encoding/NodeMarkSvg";
import { swatchColor } from "../nodeColor";
import type { ColorBy } from "../style";
import type { Command } from "./commands";
import { LINE_COPY } from "./copy";
import type { PageResult } from "./usePageResults";
import type { PanelRow } from "./SearchPanel";
import { isThink, matchTier1, placeOnce, type Candidate, type GroupId, type Placed, type SearchIndex } from "./searchGroups";

const PAGES_SHOWN = 6;
const THINK_SHOWN = 4;
const RELATED_SHOWN = 3;

export interface GroupedArgs {
  text: string;
  index: SearchIndex;
  /** Server-side hits (text, then meaning) from usePageResults; its title hits are the index's own. */
  results: readonly PageResult[];
  colorBy: ColorBy;
  views: readonly PinnedView[];
  commands: readonly Command[];
  commandRow: (c: Command) => PanelRow;
  /** Enter focuses the page, Shift+Enter adds it to the focus. */
  focusNode: (id: string, shift: boolean) => void;
  /** Enter on a set row highlights the set. */
  highlightSet: (ids: string[]) => void;
  runView: (v: PinnedView) => void;
}

/**
 * The rows of the search line while typing (flag graph-intent), grouped in a fixed order: pages, think notes, sets,
 * views, commands, then related by meaning. A group with no rows renders nothing; the "ask" slot is the Actions
 * section the shell appends. A page found twice stays in its top group with a small mark.
 */
export function groupedRows(a: GroupedArgs): PanelRow[] {
  const t1 = matchTier1(a.index, a.text);
  const cands: Candidate[] = [
    ...t1.pages.map<Candidate>((node) => ({ group: "pages", via: "title", node })),
    ...t1.think.map<Candidate>((node) => ({ group: "think", via: "title", node })),
    ...a.results
      .filter((r) => !r.related)
      .flatMap<Candidate>((r) => {
        const group = isThink(r.node) ? "think" : "pages";
        return [{ group, via: r.snippet ? "text" : "title", node: r.node, snippet: r.snippet }, ...(r.also ?? []).map<Candidate>((via) => ({ group, via, node: r.node }))];
      }),
    ...a.results.filter((r) => r.related).map<Candidate>((r) => ({ group: "related", via: "related", node: r.node, snippet: r.snippet })),
  ];
  const placed = placeOnce(cands);
  const label = (g: GroupId) => LINE_COPY.groups[g];

  const pageRow = (p: Placed, g: GroupId): PanelRow => ({
    key: `${g}:${p.node.id}`,
    section: label(g),
    label: p.node.title || p.node.id,
    detail: p.snippet,
    hint: p.node.type.replace(/-/g, " "),
    mark: p.also.length ? { text: p.also.map((v) => LINE_COPY.alsoMark[v]).join(" · "), title: p.also.map((v) => LINE_COPY.alsoTitle[v]).join("; ") } : undefined,
    lead: <NodeSwatch type={p.node.type} color={swatchColor(p.node, a.colorBy)} className="size-3.5" />,
    actions: { kind: "node", node: p.node },
    run: (shift) => a.focusNode(p.node.id, shift),
  });

  const out: PanelRow[] = [];
  placed.pages.slice(0, PAGES_SHOWN).forEach((p) => out.push(pageRow(p, "pages")));
  placed.think.slice(0, THINK_SHOWN).forEach((p) => out.push(pageRow(p, "think")));
  if (t1.set) {
    const ids = t1.set.ids;
    out.push({
      key: `set:${a.text}`,
      section: label("sets"),
      label: (
        <>
          {LINE_COPY.setRow(ids.length)} <span className="text-muted-foreground">{a.text}</span>
        </>
      ),
      lead: <Layers aria-hidden className="size-4" strokeWidth={1.6} />,
      actions: { kind: "set", ids, label: `${LINE_COPY.setRow(ids.length)} ${a.text}` },
      run: () => a.highlightSet(ids),
    });
  }
  for (const v of t1.views) {
    const view = a.views.find((x) => x.id === v.id);
    if (view)
      out.push({ key: `view:${v.id}`, section: label("views"), label: v.name, lead: <Pin aria-hidden className="size-4" strokeWidth={1.6} />, run: () => a.runView(view) });
  }
  for (const c of t1.commands) {
    const cmd = a.commands.find((x) => x.id === c.id);
    if (cmd) out.push({ ...a.commandRow(cmd), key: `command:${c.id}`, section: label("commands") });
  }
  placed.related.slice(0, RELATED_SHOWN).forEach((p) => out.push(pageRow(p, "related")));
  return out;
}
