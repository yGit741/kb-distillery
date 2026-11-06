import { useCallback, useEffect, useRef } from "react";
import { useDataSource, type LayersResult } from "@/api";
import { LINE_COPY } from "../shell/copy";
import { useShellStore, type ViewOp } from "../shell/shellStore";
import type { GNode } from "../types";
import { newLayerId, type Layer } from "./model";
import { planLayers, type Plan } from "./sentenceRun";

const asText = (e: unknown) => (e instanceof Error ? e.message : String(e));

type Op = "replace" | "stack";
interface Context {
  focus?: string;
  chosen?: Record<string, string>;
}

interface Options {
  /** The pages of the graph on screen: names in the model's answer are looked up here, like names the rules read. */
  nodes: readonly GNode[];
  /** What came of the answer: the same outcomes as a sentence the rules read (ready, a name to pick, a name no page has). */
  onPlan: (plan: Plan, typed: string, op: Op) => void;
}

/**
 * The model fallback of the `>` line (flag graph-intent): a sentence the rules cannot read is sent to
 * `POST /api/graph/layers`, which answers layer objects (never Cypher). They take the same route as rules-read layers:
 * `planLayers` resolves the names, then `onPlan` applies, asks or reports. The panel says which backend answered and,
 * when the API did, what it cost. A failure (a 422 with the model's answer, a 502 when no backend could answer) is said
 * in the panel's quiet notice and changes nothing. The last answer is kept per sentence, so picking a page from a
 * "did you mean" list does not ask (and bill) the model again.
 */
export function useLlmLayers(opts: Options): { request: (typed: string, op: Op, ctx?: Context) => void; cancel: () => void } {
  const ds = useDataSource();
  const o = useRef(opts);
  o.current = opts;
  const run = useRef(0);
  const last = useRef<{ typed: string; op: ViewOp; res: LayersResult } | null>(null);

  const settle = useCallback((res: LayersResult, typed: string, op: Op, ctx: Context) => {
    // the ids the server wrote are its own: a layer in the store gets one from the same counter as every other layer
    const layers: Layer[] = res.layers.map((l) => ({ ...(l as unknown as Layer), id: newLayerId() }));
    o.current.onPlan(planLayers(layers, res.lines, typed, o.current.nodes, ctx), typed, op);
  }, []);

  const request = useCallback(
    (typed: string, op: Op, ctx: Context = {}) => {
      const hit = last.current;
      if (hit && hit.typed === typed && hit.op === op) return settle(hit.res, typed, op, ctx);
      const mine = ++run.current;
      const store = useShellStore.getState();
      store.setShaping(true);
      store.setShapeError(null);
      store.say(LINE_COPY.asking);
      ds.layersFromText(typed, op).then(
        (res) => {
          if (run.current !== mine) return;
          const s = useShellStore.getState();
          s.setShaping(false);
          last.current = { typed, op, res };
          s.say(LINE_COPY.interpretedBy(res.backend, res.usd ?? 0, res.fallback_from));
          settle(res, typed, op, ctx);
        },
        (e: unknown) => {
          if (run.current !== mine) return;
          const s = useShellStore.getState();
          s.setShaping(false);
          s.say(asText(e));
        },
      );
    },
    [ds, settle],
  );

  const cancel = useCallback(() => {
    run.current++;
    useShellStore.getState().setShaping(false);
  }, []);
  // an answer that lands after the screen is gone must not draw on another one
  useEffect(
    () => () => {
      run.current++;
    },
    [],
  );
  return { request, cancel };
}
