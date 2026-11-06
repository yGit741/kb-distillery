import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError, DataSourceProvider, type DataSource, type ShapeResult } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleSnapshot } from "../fixtures";
import { GraphScreen, type GraphHost } from "../GraphScreen";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { useShellStore } from "./shellStore";

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
vi.mock("@/components/Markdown", () => ({ Markdown: ({ children }: { children: string }) => <div data-testid="md">{children}</div> }));

// each test mounts the whole screen: give a loaded machine room
vi.setConfig({ testTimeout: 20_000 });

const host: GraphHost = {
  openPage: vi.fn(),
  pageHref: (s) => `/app/pages/${s}`,
  clearParams: vi.fn(),
  setParams: vi.fn(),
  go: vi.fn(),
  href: (to) => `/app${to}`,
};

const noStyle = { hide_edge_kinds: [], hide_labels: [] };
/** A backend answer: rows of page slugs, and the style the text carried. */
const answer = (over: Partial<ShapeResult> = {}): ShapeResult => ({
  columns: ["i.slug"],
  rows: [["idea-margin"], ["topic-learning-theory"]],
  row_count: 2,
  truncated: false,
  cypher: "MATCH (i) RETURN i.slug",
  style: noStyle,
  style_text: "",
  source: "cypher",
  explanation: "",
  warnings: [],
  ...over,
});

function mount(over: Partial<DataSource> = {}) {
  const recent: { at: string; text: string; spec: Record<string, unknown> }[] = [];
  const ds: DataSource = mockDataSource({
    getGraph: async () => sampleSnapshot(),
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent }),
    listViews: async () => ({ views: [] }),
    addRecent: vi.fn(async (text: string, spec?: Record<string, unknown>) => {
      recent.push({ at: `2026-11-04T10:0${recent.length}:00Z`, text, spec: spec ?? {} });
      return { recent: [...recent] };
    }),
    ...over,
  });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphScreen search={{}} host={host} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return ds;
}

const box = () => screen.findByRole("combobox", { name: /search the graph/i });
/** Type a text, take the "Shape the graph" row. */
async function shapeWith(text: string) {
  await userEvent.type(await box(), text);
  await userEvent.click(await screen.findByRole("option", { name: /shape the graph/i }));
}
const hits = () => [...(useGraphUi.getState().view?.hits ?? [])].sort();

beforeEach(() => {
  localStorage.clear();
  useKb.setState({ selection: new Set() });
  useShellStore.setState({ pendingShape: null, pendingView: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0, hiddenKeys: new Set(), hiddenLinkKinds: new Set(), quick: useGraphUi.getState().quick });
});

describe("flag graph-shell off", () => {
  it("has no shaping: the Finder stays and the backend is never asked", async () => {
    await withFlag("graph-shell", false, async () => {
      const shapeGraph = vi.fn(async () => answer());
      mount({ shapeGraph });
      expect(await screen.findByRole("combobox", { name: /search a page/i })).toBeInTheDocument();
      expect(screen.queryByTestId("graph-shell")).not.toBeInTheDocument();
      // a request left in the store is not acted on without the shell
      useShellStore.getState().requestShape("colour by area");
      await new Promise((r) => setTimeout(r, 30));
      expect(shapeGraph).not.toHaveBeenCalled();
    });
  });
});

describe("flag graph-shell on: free-text shaping", () => {
  it("rows become the drawn pages, the style drives the knobs, the panel shows the canonical style", async () => {
    await withFlag("graph-shell", true, async () => {
      const shapeGraph = vi.fn(async () => answer({ style: { ...noStyle, colour_by: { by: "prop", name: "areas" }, size_by: { by: "degree" } }, style_text: "colour by areas; size by degree" }));
      mount({ shapeGraph });
      await shapeWith("MATCH (i:Idea) RETURN i.slug");
      await waitFor(() => expect(shapeGraph).toHaveBeenCalledWith("MATCH (i:Idea) RETURN i.slug"));
      await waitFor(() => expect(hits()).toEqual(["idea-margin", "topic-learning-theory"]));
      // exactly the rows: no neighbours added
      expect(useGraphUi.getState().view?.shown.size).toBe(2);
      expect(useGraphUi.getState().colorBy).toBe("area");
      expect(useGraphUi.getState().sizeBy).toBe("connections");
      // the panel closed and the notice says what happened
      await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
      // reopened: the status pill carries the canonical style text and the page count
      await userEvent.click(await box());
      expect(await screen.findByTestId("shape-status")).toHaveTextContent("colour by areas; size by degree · 2 pages");
    });
  });

  it("records the applied shape as a Recent step that reappears in the rows", async () => {
    await withFlag("graph-shell", true, async () => {
      const ds = mount({ shapeGraph: async () => answer({ style_text: "colour by areas" }) });
      await shapeWith("MATCH (i:Idea) RETURN i.slug");
      await waitFor(() => expect(ds.addRecent).toHaveBeenCalledWith("MATCH (i:Idea) RETURN i.slug", { text: "MATCH (i:Idea) RETURN i.slug", style: "colour by areas", cypher: "MATCH (i) RETURN i.slug" }));
      await userEvent.click(await box());
      expect(await screen.findByRole("option", { name: "MATCH (i:Idea) RETURN i.slug" })).toBeInTheDocument();
      expect(within(screen.getByRole("listbox")).getByText("Recent")).toBeInTheDocument();
    });
  });

  it("a style only (cypher null) keeps the pages on screen", async () => {
    await withFlag("graph-shell", true, async () => {
      mount({ shapeGraph: async () => answer({ cypher: null, rows: [], row_count: 0, style: { ...noStyle, colour_by: { by: "prop", name: "depth" } }, style_text: "colour by depth" }) });
      await screen.findByTestId("graph-shell");
      const before = { view: null };
      await shapeWith("colour by depth");
      await waitFor(() => expect(useGraphUi.getState().colorBy).toBe("depth"));
      expect(useGraphUi.getState().view).toBe(before.view);
      await userEvent.click(await box());
      expect(await screen.findByTestId("shape-status")).toHaveTextContent("colour by depth");
      expect(screen.getByTestId("shape-status")).not.toHaveTextContent(/pages/);
    });
  });

  it("layout force frees the anchored layout", async () => {
    await withFlag("graph-shell", true, async () => {
      mount({ shapeGraph: async () => answer({ cypher: null, rows: [], row_count: 0, style: { ...noStyle, layout: "force" }, style_text: "layout force" }) });
      await screen.findByTestId("graph-shell");
      useGraphUi.setState({ layoutMode: "anchored" });
      await shapeWith("layout force");
      await waitFor(() => expect(useGraphUi.getState().layoutMode).toBe("free"));
    });
  });

  it("hides a node label: the type leaves the drawn set and the pages", async () => {
    await withFlag("graph-shell", true, async () => {
      mount({
        shapeGraph: async () =>
          answer({
            rows: [["idea-margin"], ["q-why-big-nets-work"]],
            style: { ...noStyle, hide_labels: ["Question"], hide_edge_kinds: ["MENTIONS", "COLLABORATES_WITH"] },
            style_text: "hide Question; hide MENTIONS; hide COLLABORATES_WITH",
          }),
      });
      await shapeWith("MATCH (n) RETURN n.slug; hide Question; hide MENTIONS");
      await waitFor(() => expect(hits()).toEqual(["idea-margin"]));
      expect(useGraphUi.getState().shownTypes?.has("question")).toBe(false);
      // MENTIONS is two kinds of drawn link; the layout keeps them (nothing is rebuilt), they are only not drawn
      expect([...useGraphUi.getState().hiddenLinkKinds].sort()).toEqual(["related", "wikilink"]);
      await userEvent.click(await box());
      // what the graph cannot draw is said, not dropped
      expect(await screen.findByTestId("shape-status")).toHaveTextContent(/Not applied: hide COLLABORATES_WITH/);
    });
  });

  it("a clause the graph cannot draw is listed back with its reason", async () => {
    await withFlag("graph-shell", true, async () => {
      mount({ shapeGraph: async () => answer({ cypher: null, rows: [], row_count: 0, style: { ...noStyle, colour_by: { by: "label" }, layout: "grid" }, style_text: "colour by label; layout grid" }) });
      await shapeWith("colour by label");
      await waitFor(() => expect(useShellStore.getState().shape).not.toBeNull());
      await userEvent.click(await box());
      const status = await screen.findByTestId("shape-status");
      expect(status).toHaveTextContent(/colour by label \(the mark already shows the type\)/);
      expect(status).toHaveTextContent(/layout grid \(not drawn yet\)/);
      expect(useGraphUi.getState().colorBy).toBe(DEFAULT_PREFS.colorBy);
    });
  });

  it("undo from the panel gives back the pages and the style", async () => {
    await withFlag("graph-shell", true, async () => {
      mount({ shapeGraph: async () => answer({ style: { ...noStyle, colour_by: { by: "prop", name: "depth" } }, style_text: "colour by depth" }) });
      await screen.findByTestId("graph-shell");
      const was = useGraphUi.getState().colorBy;
      await shapeWith("MATCH (i) RETURN i.slug");
      await waitFor(() => expect(hits()).toHaveLength(2));
      expect(useGraphUi.getState().colorBy).toBe("depth");
      await userEvent.click(await box());
      await userEvent.click(await screen.findByRole("option", { name: /^undo/i }));
      expect(useGraphUi.getState().view).toBeNull();
      expect(useGraphUi.getState().colorBy).toBe(was);
      expect(useShellStore.getState().undo).toBeNull();
      expect(useShellStore.getState().shape).toBeNull();
    });
  });

  it("Cmd-Z undoes while the panel is closed, one level, and leaves typing alone", async () => {
    // one level is the behaviour without graph-intent (with it the layer stack keeps twenty steps: layers/store.test.ts)
    await withFlag("graph-intent", false, () => withFlag("graph-shell", true, async () => {
      let n = 0;
      mount({ shapeGraph: async () => (n++ === 0 ? answer({ rows: [["idea-margin"]], row_count: 1 }) : answer()) });
      await screen.findByTestId("graph-shell");
      await shapeWith("MATCH (i) RETURN i.slug");
      await waitFor(() => expect(hits()).toEqual(["idea-margin"]));
      await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
      await shapeWith("MATCH (j) RETURN j.slug");
      await waitFor(() => expect(hits()).toEqual(["idea-margin", "topic-learning-theory"]));
      await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
      // typing in the box keeps the text's own undo
      await userEvent.click(await box());
      await userEvent.keyboard("{Meta>}z{/Meta}");
      expect(hits()).toEqual(["idea-margin", "topic-learning-theory"]);
      await userEvent.keyboard("{Escape}");
      // closed: Cmd-Z gives back the state before the LAST shape (the first shape), once
      await userEvent.keyboard("{Meta>}z{/Meta}");
      expect(hits()).toEqual(["idea-margin"]);
      await userEvent.keyboard("{Meta>}z{/Meta}");
      expect(hits()).toEqual(["idea-margin"]);
    }));
  });

  it("a backend error is a quiet row in the panel and the graph stays as it was", async () => {
    await withFlag("graph-shell", true, async () => {
      mount({ shapeGraph: async () => Promise.reject(new ApiError("Unknown property `colour`; nodes carry slug, title, type", 422)) });
      await screen.findByTestId("graph-shell");
      await shapeWith("colour by colour");
      const row = await screen.findByTestId("shape-error");
      expect(within(row).getByText(/Unknown property/)).toBeInTheDocument();
      expect(screen.getByRole("listbox")).toBeInTheDocument();
      expect(useGraphUi.getState().view).toBeNull();
      expect(useShellStore.getState().undo).toBeNull();
      // editing the text retires the error
      await userEvent.type(await box(), "s");
      await waitFor(() => expect(screen.queryByTestId("shape-error")).not.toBeInTheDocument());
    });
  });

  it("rows that name no page of this graph change nothing and say so", async () => {
    await withFlag("graph-shell", true, async () => {
      const ds = mount({ shapeGraph: async () => answer({ rows: [[3]], row_count: 1, columns: ["count"] }) });
      await shapeWith("MATCH (n) RETURN count(n)");
      expect(await screen.findByTestId("shape-error")).toHaveTextContent(/matched no pages/i);
      expect(useGraphUi.getState().view).toBeNull();
      expect(ds.addRecent).not.toHaveBeenCalled();
    });
  });

  it("a new request replaces one still on its way: the older answer is dropped", async () => {
    await withFlag("graph-shell", true, async () => {
      let release: (r: ShapeResult) => void = () => {};
      let n = 0;
      mount({ shapeGraph: () => (n++ === 0 ? new Promise<ShapeResult>((r) => (release = r)) : Promise.resolve(answer({ rows: [["jane-doe"]], row_count: 1 }))) });
      await shapeWith("MATCH (a) RETURN a.slug");
      expect(await screen.findByTestId("shape-busy")).toBeInTheDocument();
      await userEvent.clear(await box());
      await shapeWith("MATCH (b) RETURN b.slug");
      await waitFor(() => expect(hits()).toEqual(["jane-doe"]));
      release(answer({ rows: [["idea-margin"]], row_count: 1 }));
      await new Promise((r) => setTimeout(r, 30));
      expect(hits()).toEqual(["jane-doe"]);
    });
  });

  it("undo drops an answer still on its way", async () => {
    await withFlag("graph-shell", true, async () => {
      let release: (r: ShapeResult) => void = () => {};
      let n = 0;
      mount({ shapeGraph: () => (n++ === 0 ? Promise.resolve(answer({ rows: [["idea-margin"]], row_count: 1 })) : new Promise<ShapeResult>((r) => (release = r))) });
      await shapeWith("MATCH (a) RETURN a.slug");
      await waitFor(() => expect(hits()).toEqual(["idea-margin"]));
      await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
      await shapeWith("MATCH (b) RETURN b.slug");
      expect(await screen.findByTestId("shape-busy")).toBeInTheDocument();
      await userEvent.keyboard("{Escape}");
      await userEvent.keyboard("{Meta>}z{/Meta}");
      expect(useGraphUi.getState().view).toBeNull();
      release(answer({ rows: [["jane-doe"]], row_count: 1 }));
      await new Promise((r) => setTimeout(r, 30));
      expect(useGraphUi.getState().view).toBeNull();
    });
  });

  it("a shape that cannot be drawn says so instead of failing silently", async () => {
    await withFlag("graph-shell", true, async () => {
      mount({ shapeGraph: async () => ({ ...answer(), style: null as never }) });
      await shapeWith("MATCH (a) RETURN a.slug");
      expect(await screen.findByTestId("shape-error")).toHaveTextContent(/could not draw/i);
      expect(useGraphUi.getState().view).toBeNull();
    });
  });

  it("a headline view and Reset filters bring hidden link kinds back", async () => {
    useGraphUi.setState({ hiddenLinkKinds: new Set(["wikilink"]) });
    useGraphUi.getState().resetFilters();
    expect(useGraphUi.getState().hiddenLinkKinds.size).toBe(0);
    useGraphUi.setState({ hiddenLinkKinds: new Set(["wikilink"]) });
    useGraphUi.getState().applyStory("map");
    expect(useGraphUi.getState().hiddenLinkKinds.size).toBe(0);
  });

  it("the pill goes when the shape is no longer what is drawn", async () => {
    await withFlag("graph-shell", true, async () => {
      mount({ shapeGraph: async () => answer({ style_text: "colour by areas", style: { ...noStyle, colour_by: { by: "prop", name: "areas" } } }) });
      await shapeWith("MATCH (i) RETURN i.slug");
      await waitFor(() => expect(hits()).toHaveLength(2));
      useGraphUi.setState({ view: null });
      await userEvent.click(await box());
      await screen.findByRole("listbox");
      expect(screen.queryByTestId("shape-status")).not.toBeInTheDocument();
    });
  });
});
