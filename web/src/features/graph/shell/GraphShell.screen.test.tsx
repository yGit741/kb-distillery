import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleSnapshot } from "../fixtures";
import { GraphScreen, type GraphHost } from "../GraphScreen";
import { DEFAULT_PREFS, useGraphUi } from "../store";

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

const host: GraphHost = {
  openPage: vi.fn(),
  pageHref: (s) => `/app/pages/${s}`,
  clearParams: vi.fn(),
  setParams: vi.fn(),
  go: vi.fn(),
  href: (to) => `/app${to}`,
};

const ds = (): DataSource =>
  mockDataSource({ getGraph: async () => sampleSnapshot(), search: async () => ({ hits: [], total: 0 }), listRecent: async () => ({ recent: [] }), listViews: async () => ({ views: [] }) });

const screenWith = () =>
  render(
    <DataSourceProvider source={ds()}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphScreen search={{}} host={host} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );

beforeEach(() => {
  localStorage.clear();
  useKb.setState({ selection: new Set() });
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0 });
});

describe("flag graph-shell", () => {
  it("off: the Finder stays and the shell is not there", async () => {
    await withFlag("graph-shell", false, async () => {
      screenWith();
      expect(await screen.findByRole("combobox", { name: /search a page/i })).toBeInTheDocument();
      expect(screen.queryByTestId("graph-shell")).not.toBeInTheDocument();
      expect(screen.queryByRole("combobox", { name: /search the graph/i })).not.toBeInTheDocument();
    });
  });

  it("on: the Finder is hidden and the shell's search bar replaces it", async () => {
    await withFlag("graph-shell", true, async () => {
      screenWith();
      expect(await screen.findByTestId("graph-shell")).toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: /search the graph/i })).toBeInTheDocument();
      expect(screen.queryByRole("combobox", { name: /search a page/i })).not.toBeInTheDocument();
      // the corner controls replace the toolbar
      expect(screen.queryByRole("navigation", { name: /graph tools/i })).not.toBeInTheDocument();
    });
  });

  it("on: a command from the panel drives the graph (Labels and views opens the rail)", async () => {
    await withFlag("graph-shell", true, async () => {
      screenWith();
      await userEvent.type(await screen.findByRole("combobox", { name: /search the graph/i }), "/labels");
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(useGraphUi.getState().railOpen).toBe(true));
    });
  });

  it("on: choosing a page asks the canvas to centre on it", async () => {
    await withFlag("graph-shell", true, async () => {
      screenWith();
      await userEvent.type(await screen.findByRole("combobox", { name: /search the graph/i }), "margin");
      await userEvent.click(await screen.findByRole("option", { name: /idea margin/i }));
      expect(useGraphUi.getState().focusRequest?.id).toBe("idea-margin");
    });
  });
});
