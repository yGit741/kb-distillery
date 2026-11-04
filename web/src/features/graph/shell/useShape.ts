import { useCallback, useEffect, useRef } from "react";
import { useDataSource, type ShapeResult } from "@/api";
import { useKb } from "@/lib/store";
import { useGraphUi } from "../store";
import type { GNode } from "../types";
import { dropTypes, marker, pillText, planStyle, restore, shapeIds, snapshot } from "./shape";
import { useShellStore } from "./shellStore";

interface Options {
  byId: ReadonlyMap<string, GNode>;
  /** The types drawn right now (the screen's own default when none was chosen). */
  shownTypes: ReadonlySet<string> | null;
  /** Draw exactly these pages, replacing the pages on screen (the picked view's "exact" form). */
  showExact: (ids: string[]) => void;
  /** Record an applied shape as a recent step. */
  record: (label: string, spec: Record<string, unknown>) => void;
  /** The shape was drawn: the panel may close. */
  onApplied: (text: string, notice: string) => void;
}

const asText = (e: unknown) => (e instanceof Error ? e.message : String(e));

/**
 * Free-text shaping of the graph (flag graph-shell). A request in the shell store (`requestShape`) is sent to
 * `POST /api/graph/shape`; rows become the drawn pages (a text with no selection keeps the current ones) and the
 * style drives the screen's colour, size, layout and hidden types. One level of undo is kept, and a failure is
 * said in the panel without touching the graph. The text shapes the view only, never the wiki.
 */
export function useShape(opts: Options): { undo: () => boolean } {
  const ds = useDataSource();
  const pending = useShellStore((s) => s.pendingShape);
  // the latest options, so a reply that lands after a re-render still draws against the current graph
  const o = useRef(opts);
  o.current = opts;
  const run = useRef(0);

  const apply = useCallback((text: string, res: ShapeResult) => {
    const { byId, shownTypes, showExact, record, onApplied } = o.current;
    const plan = planStyle(res.style, byId.values());
    const hidden = new Set(plan.hideTypes);
    let ids: string[] | null = null;
    if (res.cypher != null) {
      const named = shapeIds(res, byId);
      ids = named.filter((id) => !hidden.has(byId.get(id)?.type ?? ""));
      if (!ids.length) {
        useShellStore.getState().setShapeError(named.length ? "Every page it matched is hidden by the same text." : "It matched no pages in this graph.");
        return;
      }
    }
    const before = snapshot();
    const patch: Record<string, unknown> = { ...plan.patch };
    if (hidden.size) patch.shownTypes = new Set([...(shownTypes ?? Array.from(byId.values(), (n) => n.type))].filter((t) => !hidden.has(t)));
    // the colour keys clicked off in the legend belong to the colouring they were made under
    if (plan.hideLinkKinds.length) patch.hiddenLinkKinds = new Set([...useGraphUi.getState().hiddenLinkKinds, ...plan.hideLinkKinds]);
    if (plan.patch.colorBy && plan.patch.colorBy !== before.colorBy) patch.hiddenKeys = new Set();
    if (Object.keys(patch).length) useGraphUi.setState({ ...patch, story: "" });
    if (ids) showExact(ids);
    else {
      // style only: the pages on screen stay (minus a hidden type, which a view would otherwise draw past the filter)
      const view = useGraphUi.getState().view;
      if (view && hidden.size) {
        const next = dropTypes(view, hidden, byId);
        useGraphUi.setState({ view: next });
        if (next) useKb.getState().setSelection(next.hits);
        else useKb.getState().clearSelection();
      }
    }
    if (ids || plan.patch.layoutMode || hidden.size) useGraphUi.getState().fit();
    const pages = ids ? ids.length : null;
    const styleText = res.style_text.trim();
    useShellStore.getState().setShape({ text, styleText, pages, skipped: plan.skipped, after: marker() }, before);
    record(text, { text, style: styleText, ...(res.cypher ? { cypher: res.cypher } : {}) });
    onApplied(text, `Shaped: ${pillText(styleText, pages) || "no change"}. Cmd-Z undoes it.`);
  }, []);

  useEffect(() => {
    if (pending === null) return;
    const store = useShellStore.getState();
    store.clearPending();
    const text = pending.trim();
    if (!text) return;
    const mine = ++run.current;
    store.setShaping(true);
    store.setShapeError(null);
    ds.shapeGraph(text).then(
      (res) => {
        if (run.current !== mine) return;
        useShellStore.getState().setShaping(false);
        try {
          apply(text, res);
        } catch (e) {
          useShellStore.getState().setShapeError(`Could not draw that shape: ${asText(e)}`);
        }
      },
      (e: unknown) => {
        if (run.current !== mine) return;
        useShellStore.getState().setShaping(false);
        useShellStore.getState().setShapeError(asText(e));
      },
    );
  }, [pending, ds, apply]);

  // a reply that lands after the screen is gone must not draw on another one
  useEffect(
    () => () => {
      run.current++;
      // the undo and the pill belong to the graph on screen: another graph must not be restored into
      const s = useShellStore.getState();
      s.setShaping(false);
      s.clearShape();
      s.setShapeError(null);
    },
    [],
  );

  const undo = useCallback(() => {
    const store = useShellStore.getState();
    if (!store.undo) return false;
    // an answer still on its way would draw over what the person just took back
    run.current++;
    store.setShaping(false);
    restore(store.undo);
    store.clearShape();
    store.setShapeError(null);
    return true;
  }, []);
  return { undo };
}
