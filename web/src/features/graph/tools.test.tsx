import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { DataSourceProvider, type DataSource } from "@/api";
import { DRAFTS_KEY } from "@/features/scopes/logic";
import { useKb } from "@/lib/store";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { useBasket } from "./basket";
import { rawSnapshot, sampleSnapshot } from "./fixtures";
import { GraphScreen, type GraphHost } from "./GraphScreen";
import { useLayer } from "./layerStore";
import { MENU_ITEMS } from "./menu";
import { DEFAULT_PREFS, useGraphUi } from "./store";
import { RegionOverlay } from "./tools/RegionOverlay";
import { TOOLS, type GraphToolContext } from "./tools";
import { node } from "./fixtures";

// jsdom has no canvas: stand in for force-graph with a chainable no-op instance.
vi.mock("force-graph", () => {
  const getters: Record<string, (args: unknown[]) => unknown> = {
    zoom: (a) => (a.length ? undefined : 1),
    centerAt: (a) => (a.length ? undefined : { x: 0, y: 0 }),
    graphData: (a) => (a.length ? undefined : { nodes: [], links: [] }),
    d3Force: () => ({ strength: () => {}, distance: () => {} }),
    screen2GraphCoords: () => ({ x: 0, y: 0 }),
    graph2ScreenCoords: () => ({ x: 0, y: 0 }),
  };
  const make = () => {
    const inst: Record<string, unknown> = {};
    const proxy: unknown = new Proxy(inst, {
      get: (_t, name: string) => (name === "_destructor" ? () => {} : (...args: unknown[]) => (name in getters ? getters[name]?.(args) ?? proxy : proxy)),
    });
    return proxy;
  };
  return { default: () => () => make() };
});
vi.mock("@/components/Markdown", () => ({ Markdown: ({ children }: { children: string }) => <div>{children}</div> }));

// jsdom has no PointerEvent: a MouseEvent that carries the pointer id is enough for the gestures
if (typeof globalThis.PointerEvent === "undefined") {
  class PointerEventStub extends MouseEvent {
    readonly pointerId: number;
    constructor(type: string, init: MouseEventInit & { pointerId?: number } = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
    }
  }
  (globalThis as unknown as { PointerEvent: unknown }).PointerEvent = PointerEventStub;
}

const host = (): GraphHost => ({
  openPage: vi.fn(),
  pageHref: (s) => `/app/pages/${s}`,
  clearParams: vi.fn(),
  setParams: vi.fn(),
  go: vi.fn(),
  href: (to, search) => `/app${to}${search ? `?${new URLSearchParams(search)}` : ""}`,
});

function wrap(ds: DataSource, ui: ReactNode) {
  return (
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>
    </DataSourceProvider>
  );
}

const corpusTable = {
  format: "printed-docs",
  count: 4,
  columns: [],
  rows: [
    { path: "raw/printed-docs/2019-fine-grained.pdf", sha1: "", title: "Fine grained", digestion: "easy", collection: [], disposition: "source", slug: "2019-fine-grained", year: 2019 },
    { path: "raw/printed-docs/2019-fine-grained-ink.pdf", sha1: "", title: "", digestion: "", collection: [], disposition: "ink:raw/printed-docs/2019-fine-grained.pdf" },
    { path: "raw/printed-docs/2021-new-idea.pdf", sha1: "", title: "New idea", digestion: "", collection: ["course-runi-rl"], disposition: "queued", year: 2021 },
  ],
};
const preview = { path: "raw/printed-docs/2021-new-idea.pdf", exists: true, ext: "pdf", file_url: "/api/raw/raw/printed-docs/2021-new-idea.pdf/file", format: "printed-docs", text: "Abstract. We show", slug: null };

const make = (o: Partial<DataSource> = {}) =>
  mockDataSource({ getGraph: vi.fn(async (opts?: { raw?: boolean }) => (opts?.raw ? rawSnapshot() : sampleSnapshot())), ...o });

beforeEach(() => {
  localStorage.clear();
  useBasket.getState().reload();
  useLayer.setState({ rawOn: false, drawer: null, expansions: [] });
  useKb.setState({ selection: new Set() });
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0 });
});

/** Open a tool's panel the way a command or its key does: through the store's flyout (the panels host draws it). */
const open = async (name: RegExp) => {
  await screen.findByTestId("graph-stats");
  const tool = TOOLS.find((t) => name.test(t.label));
  if (!tool) throw new Error(`no tool named ${name}`);
  act(() => useGraphUi.setState({ railOpen: false, flyout: tool.id }));
  await screen.findByRole("region", { name: tool.label });
};

describe("selection tool: expand, collapse, path", () => {
  it("adds neighbours over the drawn links, then Collapse takes the step back", async () => {
    render(wrap(make(), <GraphScreen search={{}} host={host()} />));
    await open(/^selection/i);
    act(() => useKb.getState().setSelection(["idea-margin"]));
    await userEvent.click(screen.getByRole("button", { name: "+ Neighbours" }));
    expect([...useKb.getState().selection].sort()).toEqual(["idea-margin", "topic-learning-theory"]);
    expect(screen.getByRole("button", { name: "Collapse" })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Collapse" }));
    expect([...useKb.getState().selection]).toEqual(["idea-margin"]);
    expect(screen.getByRole("button", { name: "Collapse" })).toBeDisabled();
  });

  it("+ Sources selects the sources under a concept and draws them", async () => {
    render(wrap(make(), <GraphScreen search={{}} host={host()} />));
    await open(/^selection/i);
    act(() => useKb.getState().setSelection(["idea-margin"]));
    await userEvent.click(screen.getByRole("button", { name: "+ Sources" }));
    expect([...useKb.getState().selection].sort()).toEqual(["2019-fine-grained", "2020-listed-paper", "idea-margin"]);
    expect(useGraphUi.getState().revealed.has("2019-fine-grained")).toBe(true);
  });

  it("+ Citations adds the papers that cite or are cited by the selection", async () => {
    const getCitations = vi.fn(async () => ({ nodes: [], links: [{ source: "2019-fine-grained", target: "2020-listed-paper" }] }));
    render(wrap(make({ getCitations }), <GraphScreen search={{}} host={host()} />));
    await open(/^selection/i);
    act(() => useKb.getState().setSelection(["2019-fine-grained"]));
    await userEvent.click(screen.getByRole("button", { name: "+ Citations" }));
    await waitFor(() => expect([...useKb.getState().selection].sort()).toEqual(["2019-fine-grained", "2020-listed-paper"]));
  });

  it("finds the shortest path between two selected pages through the path endpoint", async () => {
    const findPath = vi.fn(async () => ({ a: "jane-doe", b: "idea-margin", distance: 2, paths: [{ nodes: ["jane-doe", "topic-learning-theory", "idea-margin"], hops: [] }] }));
    render(wrap(make({ findPath }), <GraphScreen search={{}} host={host()} />));
    await open(/^selection/i);
    const go = screen.getByRole("button", { name: "Path between two" });
    act(() => useKb.getState().setSelection(["jane-doe"]));
    expect(go).toBeDisabled();
    act(() => useKb.getState().setSelection(["jane-doe", "idea-margin"]));
    await userEvent.click(go);
    expect(findPath).toHaveBeenCalledWith("jane-doe", "idea-margin");
    await waitFor(() => expect(useKb.getState().selection.has("topic-learning-theory")).toBe(true));
    expect(useGraphUi.getState().revealed.has("jane-doe")).toBe(true);
    expect(await screen.findByText(/path of 3 pages \(2 links\)/i)).toBeInTheDocument();
  });

  it("says so when two pages are not connected", async () => {
    render(wrap(make({ findPath: async () => ({ a: "x", b: "y", paths: [] }) }), <GraphScreen search={{}} host={host()} />));
    await open(/^selection/i);
    act(() => useKb.getState().setSelection(["jane-doe", "idea-margin"]));
    await userEvent.click(screen.getByRole("button", { name: "Path between two" }));
    expect(await screen.findByText(/not connected/i)).toBeInTheDocument();
  });
});

describe("right-drag selection", () => {
  const stubCtx = (select = vi.fn(), clearSelection = vi.fn()): GraphToolContext => {
    const at: Record<string, { x: number; y: number }> = { a: { x: 20, y: 20 }, b: { x: 200, y: 200 } };
    return {
      model: { nodes: [], links: [], conceptLinks: [] },
      byId: new Map(),
      visible: new Set(["a", "b"]),
      selection: new Set(),
      select,
      clearSelection,
      focus: vi.fn(),
      screenOf: (id) => at[id] ?? null,
      openReader: vi.fn(),
    };
  };
  const setup = (ctx: GraphToolContext) => {
    const r = render(
      <div data-testid="graph-screen">
        <canvas data-testid="cv" />
        <RegionOverlay ctx={ctx} />
      </div>,
    );
    return { canvas: r.getByTestId("cv") as HTMLCanvasElement };
  };

  it("a right-drag box selects what it covers; Shift adds", () => {
    const select = vi.fn();
    const { canvas } = setup(stubCtx(select));
    fireEvent.pointerDown(canvas, { button: 2, clientX: 0, clientY: 0, pointerId: 1 });
    fireEvent.pointerMove(window, { clientX: 100, clientY: 100, pointerId: 1 });
    expect(screen.getByTestId("region-box")).toBeInTheDocument();
    fireEvent.pointerUp(window, { button: 2, clientX: 100, clientY: 100, pointerId: 1 });
    expect(select).toHaveBeenCalledWith(["a"], { additive: false });
    expect(screen.queryByTestId("region-box")).not.toBeInTheDocument();
    fireEvent.pointerDown(canvas, { button: 2, clientX: 0, clientY: 0, pointerId: 2, shiftKey: true });
    fireEvent.pointerMove(window, { clientX: 300, clientY: 300, pointerId: 2 });
    fireEvent.pointerUp(window, { button: 2, clientX: 300, clientY: 300, pointerId: 2 });
    expect(select).toHaveBeenLastCalledWith(["a", "b"], { additive: true });
  });

  it("an empty box clears the selection, a plain right-click does nothing here", () => {
    const select = vi.fn();
    const clear = vi.fn();
    const { canvas } = setup(stubCtx(select, clear));
    fireEvent.pointerDown(canvas, { button: 2, clientX: 400, clientY: 400, pointerId: 1 });
    fireEvent.pointerMove(window, { clientX: 450, clientY: 450, pointerId: 1 });
    fireEvent.pointerUp(window, { button: 2, clientX: 450, clientY: 450, pointerId: 1 });
    expect(clear).toHaveBeenCalledTimes(1);
    fireEvent.pointerDown(canvas, { button: 2, clientX: 5, clientY: 5, pointerId: 2 });
    fireEvent.pointerUp(window, { button: 2, clientX: 5, clientY: 5, pointerId: 2 });
    expect(clear).toHaveBeenCalledTimes(1);
    expect(select).not.toHaveBeenCalled();
  });

  it("Cmd+right-drag draws a lasso that adds", () => {
    const select = vi.fn();
    const { canvas } = setup(stubCtx(select));
    fireEvent.pointerDown(canvas, { button: 2, clientX: 0, clientY: 0, pointerId: 1, metaKey: true });
    for (const [x, y] of [[60, 0], [60, 60], [0, 60]] as const) fireEvent.pointerMove(window, { clientX: x, clientY: y, pointerId: 1 });
    expect(screen.getByTestId("region-lasso")).toBeInTheDocument();
    fireEvent.pointerUp(window, { button: 2, clientX: 0, clientY: 30, pointerId: 1 });
    expect(select).toHaveBeenCalledWith(["a"], { additive: true });
  });

  it("only the canvas starts a gesture", () => {
    const select = vi.fn();
    setup(stubCtx(select));
    const btn = document.body.appendChild(document.createElement("button"));
    fireEvent.pointerDown(btn, { button: 2, clientX: 0, clientY: 0, pointerId: 1 });
    fireEvent.pointerMove(window, { clientX: 100, clientY: 100, pointerId: 1 });
    expect(screen.queryByTestId("region-box")).not.toBeInTheDocument();
  });
});

describe("basket", () => {
  it("adds the raw files under the selection to a scope draft in the Scopes format, then links to it", async () => {
    const resolveScope = vi.fn(async () => ({
      paths: ["raw/printed-docs/2019-fine-grained.pdf"],
      rows: [
        { path: "raw/printed-docs/2019-fine-grained.pdf", format: "printed-docs", disposition: "source", slug: "2019-fine-grained", page_type: null, digestion: "easy", collection: [], year: 2019 },
        { path: "raw/printed-docs/2019-fine-grained-ink.pdf", format: "printed-docs", disposition: "ink:raw/printed-docs/2019-fine-grained.pdf", slug: null, page_type: null, digestion: "", collection: [], year: null },
      ],
    }));
    const h = host();
    render(wrap(make({ resolveScope, listScopes: async () => ({ scopes: [] }) }), <GraphScreen search={{}} host={h} />));
    await open(/^scope draft/i);
    const add = screen.getByRole("button", { name: /add the raw files of 0 selected pages/i });
    expect(add).toBeDisabled();
    act(() => useKb.getState().setSelection(["idea-margin"]));
    await userEvent.click(screen.getByRole("button", { name: /add the raw files of 1 selected page$/i }));
    expect(await screen.findByText(/name the new scope first/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Scope name"), "My topic");
    await userEvent.click(screen.getByRole("button", { name: /add the raw files of 1 selected page$/i }));
    expect(resolveScope).toHaveBeenCalledWith({ nodes: ["idea-margin"] });
    expect(await screen.findByText(/1 new file/)).toBeInTheDocument();
    const stored = JSON.parse(localStorage.getItem(DRAFTS_KEY) ?? "{}");
    expect(stored.active).toBe("scope-my-topic");
    expect(stored.drafts["scope-my-topic"]).toMatchObject({ slug: "scope-my-topic", title: "My topic", isNew: true });
    expect(stored.drafts["scope-my-topic"].rows).toHaveLength(1);
    await userEvent.click(screen.getByRole("button", { name: "Make scope" }));
    expect(h.go).toHaveBeenCalledWith("/scopes", { draft: "scope-my-topic" });
  });

  it("removes a file and discards the draft", async () => {
    useBasket.getState().add({ slug: "scope-x", title: "X", isNew: true }, [
      { path: "raw/emails/t/thread.md", format: "emails", disposition: "queued", slug: null, page_type: null, digestion: "", collection: [], year: null },
    ]);
    render(wrap(make({ listScopes: async () => ({ scopes: [] }) }), <GraphScreen search={{}} host={host()} />));
    await open(/^scope draft/i);
    await userEvent.click(screen.getByRole("button", { name: /remove t\/thread\.md/i }));
    expect(useBasket.getState().store.drafts["scope-x"]?.rows).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    expect(screen.getByText(/no draft yet/i)).toBeInTheDocument();
  });
});

describe("data layer and corpus drawer", () => {
  const rawDs = (o: Partial<DataSource> = {}) => make({ getCorpus: vi.fn(async () => corpusTable as never), getRawPreview: vi.fn(async () => preview as never), ...o });

  it("?raw=1 loads the data layer and lists a pile per format", async () => {
    const ds = rawDs();
    render(wrap(ds, <GraphScreen search={{ raw: "1" }} host={host()} />));
    await open(/^raw files/i);
    expect(await screen.findByRole("button", { name: /printed-docs/ })).toHaveTextContent("10 · 57% digested");
    expect(ds.getGraph).toHaveBeenCalledWith({ raw: true });
    expect(screen.getByRole("button", { name: /emails/ })).toBeInTheDocument();
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("3 of 7 pages");
  });

  it("the checkbox switches the layer on and off", async () => {
    const ds = rawDs();
    render(wrap(ds, <GraphScreen search={{}} host={host()} />));
    await open(/^raw files/i);
    expect(screen.queryByRole("list", { name: "Piles" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: /show raw files as piles/i }));
    expect(await screen.findByRole("list", { name: "Piles" })).toBeInTheDocument();
    expect(localStorage.getItem("kb-graph-raw-layer-v1")).toBe("1");
    await userEvent.click(screen.getByRole("checkbox", { name: /show raw files as piles/i }));
    await waitFor(() => expect(screen.queryByRole("list", { name: "Piles" })).not.toBeInTheDocument());
  });

  it("a pile opens its files with companions folded; a row previews and offers Pipeline", async () => {
    const h = host();
    render(wrap(rawDs(), <GraphScreen search={{ raw: "1" }} host={h} />));
    await open(/^raw files/i);
    await userEvent.click(await screen.findByRole("button", { name: /printed-docs/ }));
    const drawer = await screen.findByRole("region", { name: "printed-docs files" });
    expect(await within(drawer).findByRole("button", { name: "2019-fine-grained.pdf" })).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "2019-fine-grained-ink.pdf" })).not.toBeInTheDocument();
    expect(within(drawer).getByTestId("drawer-count")).toHaveTextContent("2 of 2 files · 1 companions folded");
    await userEvent.click(within(drawer).getByRole("button", { name: "queued 1" }));
    expect(within(drawer).getByTestId("drawer-count")).toHaveTextContent("1 of 2 files");
    await userEvent.click(within(drawer).getByRole("button", { name: "2021-new-idea.pdf" }));
    expect(await within(drawer).findByText("Abstract. We show")).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Open file" })).toHaveAttribute("href", preview.file_url);
    await userEvent.click(within(drawer).getByRole("link", { name: "Open in Pipeline" }));
    expect(h.go).toHaveBeenCalledWith("/pipeline", { item: "raw/printed-docs/2021-new-idea.pdf" });
    await userEvent.click(within(drawer).getByRole("button", { name: "Add to scope draft" }));
    expect(await within(drawer).findByText(/added to the scope draft/i)).toBeInTheDocument();
    expect(useBasket.getState().store.drafts["scope-untitled-scope"]?.rows.map((r) => r.path)).toEqual(["raw/printed-docs/2021-new-idea.pdf"]);
  });

  it("digests only after an in-app confirmation, once", async () => {
    const digestRaw = vi.fn(async () => ({ command: "easy-digest", exit: 0, stdout: "wrote paper-x", stderr: "" }));
    render(wrap(rawDs({ digestRaw }), <GraphScreen search={{ raw: "1" }} host={host()} />));
    await open(/^raw files/i);
    await userEvent.click(await screen.findByRole("button", { name: /printed-docs/ }));
    const drawer = await screen.findByRole("region", { name: "printed-docs files" });
    await userEvent.click(await within(drawer).findByRole("button", { name: "2021-new-idea.pdf" }));
    await userEvent.click(await within(drawer).findByRole("button", { name: "Easy-digest…" }));
    expect(digestRaw).not.toHaveBeenCalled();
    await userEvent.click(within(drawer).getByRole("button", { name: "Cancel" }));
    expect(digestRaw).not.toHaveBeenCalled();
    await userEvent.click(within(drawer).getByRole("button", { name: "Easy-digest…" }));
    await userEvent.click(within(drawer).getByRole("button", { name: "Run easy-digest" }));
    await waitFor(() => expect(digestRaw).toHaveBeenCalledTimes(1));
    expect(digestRaw).toHaveBeenCalledWith("raw/printed-docs/2021-new-idea.pdf");
    expect(await within(drawer).findByText(/wrote paper-x/)).toBeInTheDocument();
  });

  it("a digested file offers no digest button", async () => {
    render(wrap(rawDs(), <GraphScreen search={{ raw: "1" }} host={host()} />));
    await open(/^raw files/i);
    await userEvent.click(await screen.findByRole("button", { name: /printed-docs/ }));
    const drawer = await screen.findByRole("region", { name: "printed-docs files" });
    await userEvent.click(await within(drawer).findByRole("button", { name: "2019-fine-grained.pdf" }));
    await within(drawer).findByRole("complementary", { name: "File preview" });
    expect(within(drawer).queryByRole("button", { name: "Easy-digest…" })).not.toBeInTheDocument();
  });

  it("lists the raw files behind the selection", async () => {
    const resolveScope = vi.fn(async () => ({ paths: [], rows: [{ path: "raw/emails/t/thread.md", format: "emails", disposition: "queued", slug: null, page_type: null, digestion: "", collection: [], year: null }] }));
    render(wrap(rawDs({ resolveScope }), <GraphScreen search={{}} host={host()} />));
    await open(/^raw files/i);
    act(() => useKb.getState().setSelection(["idea-margin"]));
    await userEvent.click(screen.getByRole("button", { name: /raw files behind 1 selected page/i }));
    const drawer = await screen.findByRole("region", { name: "Raw files behind the selection" });
    expect(await within(drawer).findByRole("button", { name: "t/thread.md" })).toBeInTheDocument();
    expect(resolveScope).toHaveBeenCalledWith({ nodes: ["idea-margin"] });
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Raw files behind the selection" })).not.toBeInTheDocument();
    expect([...useKb.getState().selection]).toEqual(["idea-margin"]);
  });
});

describe("citation genealogy", () => {
  const citations = {
    nodes: [
      { id: "2019-fine-grained", title: "Fine grained", year: 2019, citationCount: 9 },
      { id: "2020-listed-paper", title: "Listed", year: 2020, citationCount: 1 },
    ],
    links: [{ source: "2020-listed-paper", target: "2019-fine-grained" }],
  };

  it("is a menu entry for papers only", () => {
    const item = MENU_ITEMS.find((i) => i.id === "genealogy");
    expect(item?.enabled?.(node("p", { type: "paper" }))).toBe(true);
    expect(item?.enabled?.(node("i", { type: "idea" }))).toBe(false);
    expect(item?.why).toBe("papers only");
  });

  it("opens a drawer with the paper's two-hop genealogy over /api/citations", async () => {
    const getCitations = vi.fn(async () => citations as never);
    render(wrap(make({ getCitations }), <GraphScreen search={{}} host={host()} />));
    await screen.findByTestId("graph-stats");
    act(() => MENU_ITEMS.find((i) => i.id === "genealogy")?.run(node("2019-fine-grained", { type: "paper", layer: "source" }), { openReader: vi.fn(), openDetails: vi.fn(), openPage: vi.fn() }));
    const drawer = await screen.findByRole("region", { name: "Citation genealogy" });
    expect(await within(drawer).findByTestId("genealogy-bar")).toHaveTextContent("Genealogy of 2019 fine grained · 2 hops");
    expect(within(drawer).getByTestId("genealogy-bar")).toHaveTextContent("cite it 1");
    expect(getCitations).toHaveBeenCalledTimes(1);
  });

  it("explains missing citation data", async () => {
    render(wrap(make({ getCitations: async () => ({ nodes: [], links: [], missing: true }) }), <GraphScreen search={{}} host={host()} />));
    await screen.findByTestId("graph-stats");
    act(() => useLayer.getState().openDrawer({ kind: "genealogy", focus: "2019-fine-grained" }));
    expect(await screen.findByText(/no citation data yet/i)).toBeInTheDocument();
  });
});

describe("typed relations (flag graph-relations)", () => {
  const relations = [
    { source: "idea-margin", target: "topic-learning-theory", kind: "extends", origin: "stored", note: "the margin argument carries over", weight: 1 },
    { source: "2019-fine-grained", target: "idea-margin", kind: "mentions", origin: "computed", note: "", weight: 1 },
    { source: "2020-listed-paper", target: "idea-margin", kind: "mentions", origin: "computed", note: "", weight: 1 },
  ];
  const withRelations = (o: Partial<DataSource> = {}) => make({ getGraph: vi.fn(async () => sampleSnapshot({ relations })), ...o });
  const details = async () => {
    await screen.findByTestId("graph-stats");
    act(() => useKb.getState().setSelection(["idea-margin"]));
    await userEvent.click(await screen.findByRole("button", { name: "Details" }));
    return screen.findByRole("complementary", { name: "Selected page" });
  };

  it("flag off: no query tool and the inspector lists connected pages as before", () =>
    withFlag("graph-relations", false, async () => {
      const listGraphQueries = vi.fn(async () => []);
      render(wrap(withRelations({ listGraphQueries }), <GraphScreen search={{}} host={host()} />));
      const panel = await details();
      // the tool is off: nothing answers to its id, so no panel opens
      act(() => useGraphUi.setState({ flyout: "query" }));
      expect(screen.queryByRole("region", { name: "Graph query" })).not.toBeInTheDocument();
      expect(panel.querySelectorAll("details")).toHaveLength(2);
      expect(within(panel).queryByText(/extends/)).not.toBeInTheDocument();
      expect(listGraphQueries).not.toHaveBeenCalled();
    }));

  it("flag on: connected pages are grouped by kind, stated kinds open and computed ones collapsed", () =>
    withFlag("graph-relations", true, async () => {
      render(wrap(withRelations(), <GraphScreen search={{}} host={host()} />));
      const panel = await details();
      const groups = [...panel.querySelectorAll("details details")] as HTMLDetailsElement[];
      expect(groups.map((g) => g.querySelector("summary")?.textContent)).toEqual(["extends · 1", "mentions · 2 · computed"]);
      expect(groups.map((g) => g.open)).toEqual([true, false]);
      expect(within(groups[0] as HTMLElement).getByText("the margin argument carries over")).toBeInTheDocument();
    }));

  it("flag on without relations in the snapshot: the inspector stays the flat list", () =>
    withFlag("graph-relations", true, async () => {
      render(wrap(make(), <GraphScreen search={{}} host={host()} />));
      const panel = await details();
      expect(panel.querySelectorAll("details details")).toHaveLength(0);
    }));

  it("flag on: the query panel runs a named query and highlights the pages it returns", () =>
    withFlag("graph-relations", true, async () => {
      const listGraphQueries = vi.fn(async () => [{ name: "unaddressed-questions", description: "question pages nothing addresses", params: [] }]);
      const runGraphQuery = vi.fn(async () => ({ columns: ["slug", "title"], rows: [["q-why-big-nets-work", "Why big nets work"], ["not-a-page", "x"]], row_count: 2, truncated: false }));
      render(wrap(withRelations({ listGraphQueries, runGraphQuery }), <GraphScreen search={{}} host={host()} />));
      await open(/^graph query/i);
      await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Named query" }), "unaddressed-questions");
      await userEvent.click(screen.getByRole("button", { name: "Run named query" }));
      expect(runGraphQuery).toHaveBeenCalledWith("unaddressed-questions", {});
      expect(await screen.findByRole("cell", { name: "Why big nets work" })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: "Highlight 1" }));
      expect([...useKb.getState().selection]).toEqual(["q-why-big-nets-work"]);
    }));

  it("flag on: a rejected Cypher query shows the reason", () =>
    withFlag("graph-relations", true, async () => {
      const runCypher = vi.fn(async () => {
        throw new Error("unsupported clause CREATE");
      });
      render(wrap(withRelations({ listGraphQueries: async () => [], runCypher }), <GraphScreen search={{}} host={host()} />));
      await open(/^graph query/i);
      await userEvent.type(screen.getByRole("textbox", { name: /cypher/i }), "CREATE (n)");
      await userEvent.click(screen.getByRole("button", { name: "Run Cypher" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("unsupported clause CREATE");
    }));
});
