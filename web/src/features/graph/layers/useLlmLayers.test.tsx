import { act, render, waitFor } from "@testing-library/react";
import { DataSourceProvider, createHttpDataSource } from "@/api";
import { LINE_COPY } from "../shell/copy";
import { useShellStore } from "../shell/shellStore";
import { node, sampleNodes } from "../fixtures";
import type { Plan } from "./sentenceRun";
import { useLlmLayers } from "./useLlmLayers";

const nodes = [...sampleNodes, node("learning-theory", { title: "Learning theory" }), node("learning-curves", { title: "Learning curves" }), node("learning-rates", { title: "Learning rates" })];

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const answer = (over: Record<string, unknown> = {}) => ({
  layers: [{ id: "llm-1", kind: "show", target: "nodes", text: "", subgraph: { nodes: [{ t: "hops", of: "Learning theory", n: 2 }] } }],
  lines: ['show nodes within 2 hops of "Learning theory"'],
  explanation: "",
  backend: "subscription",
  fallback_from: null,
  usd: 0,
  warnings: [],
  ...over,
});

let hook: ReturnType<typeof useLlmLayers>;
const plans: { plan: Plan; typed: string; op: string }[] = [];

function Harness() {
  hook = useLlmLayers({ nodes, onPlan: (plan, typed, op) => plans.push({ plan, typed, op }) });
  return null;
}

function mount(f: ReturnType<typeof vi.fn>) {
  const ds = createHttpDataSource(f as unknown as typeof fetch);
  render(
    <DataSourceProvider source={ds}>
      <Harness />
    </DataSourceProvider>,
  );
}

const bodyOf = async (f: ReturnType<typeof vi.fn>, i = 0) => JSON.parse(await (f.mock.calls[i]![0] as Request).clone().text());
const said = () => useShellStore.getState().notice?.text;

beforeEach(() => {
  plans.length = 0;
  useShellStore.setState({ notice: null, shaping: false, shapeError: null });
});

describe("useLlmLayers", () => {
  it("posts the sentence to /api/graph/layers and plans the layers it gets back, names resolved", async () => {
    const f = vi.fn((..._a: unknown[]) => json(answer()));
    mount(f);
    act(() => hook.request("things near learning", "stack"));
    expect(useShellStore.getState().shaping).toBe(true);
    expect(said()).toBe(LINE_COPY.asking);
    await waitFor(() => expect(plans).toHaveLength(1));
    const req = f.mock.calls[0]![0] as Request;
    expect(req.url).toMatch(/\/api\/graph\/layers$/);
    expect(await bodyOf(f)).toEqual({ text: "things near learning", op: "stack" });
    const { plan, op } = plans[0]!;
    expect(op).toBe("stack");
    expect(plan.kind).toBe("ready");
    if (plan.kind !== "ready") return;
    // the name "Learning theory" is a page title here: it became its slug, and the layer got an id of the app's own
    expect(plan.layers[0]!.subgraph.nodes).toEqual([{ t: "hops", of: "learning-theory", n: 2 }]);
    expect(plan.layers[0]!.id).not.toBe("llm-1");
    expect(plan.layers[0]!.text).toBe("things near learning");
    expect(useShellStore.getState().shaping).toBe(false);
    expect(said()).toBe(LINE_COPY.interpretedBy("subscription", 0, null));
    expect(said()).not.toMatch(/\$/);
  });

  it("says which backend answered and the cost when the API did", async () => {
    mount(vi.fn((..._a: unknown[]) => json(answer({ backend: "api", fallback_from: "subscription", usd: 0.0012 }))));
    act(() => hook.request("calmer", "replace"));
    await waitFor(() => expect(plans).toHaveLength(1));
    expect(said()).toBe("Interpreted by api, about $0.0012 (subscription did not answer).");
  });

  it("shows the 422 detail in the notice and plans nothing", async () => {
    const detail = 'the reply is not a valid list of layers: 0.kind: Input should be show (answer: {"layers": [{"kind": "explode"}]})';
    mount(vi.fn((..._a: unknown[]) => json({ detail }, 422)));
    act(() => hook.request("explode it", "replace"));
    await waitFor(() => expect(said()).toBe(detail));
    expect(plans).toHaveLength(0);
    expect(useShellStore.getState().shaping).toBe(false);
  });

  it("says a 502 and a network failure the same quiet way", async () => {
    mount(vi.fn((..._a: unknown[]) => json({ detail: "the subscription backend failed: boom" }, 502)));
    act(() => hook.request("x", "replace"));
    await waitFor(() => expect(said()).toBe("the subscription backend failed: boom"));
    expect(plans).toHaveLength(0);
  });

  it("an ambiguous name asks, and picking one reuses the answer without asking the model again", async () => {
    const f = vi.fn((..._a: unknown[]) => json(answer({ layers: [{ id: "x", kind: "show", target: "nodes", text: "", subgraph: { nodes: [{ t: "hops", of: "Learning", n: 1 }] } }] })));
    mount(f);
    act(() => hook.request("near learning", "replace"));
    await waitFor(() => expect(plans).toHaveLength(1));
    expect(plans[0]!.plan.kind).toBe("ask");
    act(() => hook.request("near learning", "replace", { chosen: { Learning: "learning-curves" } }));
    expect(f).toHaveBeenCalledTimes(1);
    expect(plans).toHaveLength(2);
    const second = plans[1]!.plan;
    expect(second.kind).toBe("ready");
    if (second.kind === "ready") expect(second.layers[0]!.subgraph.nodes).toEqual([{ t: "hops", of: "learning-curves", n: 1 }]);
  });

  it("an answer that lands after a newer request is dropped", async () => {
    const slow: ((r: Response) => void)[] = [];
    const f = vi.fn((..._a: unknown[]) => new Promise<Response>((res) => slow.push(res)));
    mount(f);
    act(() => hook.request("first", "replace"));
    act(() => hook.request("second", "replace"));
    const mk = (t: string) => new Response(JSON.stringify(answer({ explanation: t })), { status: 200, headers: { "Content-Type": "application/json" } });
    slow[0]!(mk("first"));
    slow[1]!(mk("second"));
    await waitFor(() => expect(plans).toHaveLength(1));
    expect(plans[0]!.typed).toBe("second");
  });
});
