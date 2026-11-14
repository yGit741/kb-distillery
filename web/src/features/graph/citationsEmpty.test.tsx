import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { sampleSnapshot } from "./fixtures";
import { GraphScreen, type GraphHost } from "./GraphScreen";
import { DEFAULT_PREFS, useGraphUi } from "./store";

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

const host: GraphHost = { openPage: vi.fn(), pageHref: (s) => `/app/pages/${s}`, clearParams: vi.fn(), setParams: vi.fn(), go: vi.fn(), href: (to) => `/app${to}` };

const mount = () =>
  render(
    <DataSourceProvider source={mockDataSource({ getGraph: async () => ({ ...sampleSnapshot(), relations: [] }) as never, search: async () => ({ hits: [], total: 0 }) })}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphScreen search={{}} host={host} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );

beforeEach(() => {
  localStorage.clear();
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", edgeStory: "", shownTypes: null });
});
afterEach(() => vi.restoreAllMocks());

describe("the Citations view on a knowledge base with no cites links", () => {
  it("says so plainly instead of drawing an empty canvas", async () => {
    await withFlag("graph-relations", true, async () => {
      mount();
      act(() => useGraphUi.setState({ story: "citations", edgeStory: "citations" }));
      expect(await screen.findByTestId("no-citation-links")).toHaveTextContent("no citation links yet");
    });
  });

  it("shows no such message in Concepts", async () => {
    mount();
    await screen.findByTestId("graph-canvas").catch(() => undefined);
    expect(screen.queryByTestId("no-citation-links")).toBeNull();
  });
});

describe("hiding the Citations view's own page types", () => {
  it("drops its links and its chip together, so nothing still says Citations", () => {
    const all = ["paper", "concept", "topic"];
    useGraphUi.setState({ story: "citations", edgeStory: "citations", shownTypes: new Set(["paper"]) });
    act(() => useGraphUi.getState().toggleType("paper", all, all));
    expect(useGraphUi.getState().story).toBe("");
    expect(useGraphUi.getState().edgeStory).toBe("");
  });
});
