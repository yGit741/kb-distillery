import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { DataSourceProvider, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleSnapshot } from "../../fixtures";
import { GraphScreen, type GraphHost } from "../../GraphScreen";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { resetCorners } from "./cornersStore";
import type { PinnedView } from "@/api";
import { useShellStore } from "../shellStore";

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

function wrap(ds: DataSource, ui: ReactNode) {
  return (
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>
    </DataSourceProvider>
  );
}
const graph = () => mockDataSource({ getGraph: async () => sampleSnapshot() });

beforeEach(() => {
  localStorage.clear();
  resetCorners();
  useKb.setState({ selection: new Set() });
  useGraphUi.setState({ ...DEFAULT_PREFS, shownTypes: undefined, predicate: null, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0 });
});

describe("graph-shell: the corner controls on the Graph screen", () => {
  it("flag off: no corners; the Legend stays and there is no tool column", () =>
    withFlag("graph-shell", false, async () => {
      render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      expect(await screen.findByRole("region", { name: "Legend" })).toBeInTheDocument();
      expect(screen.queryByRole("navigation", { name: "Graph tools" })).toBeNull();
      expect(screen.queryByTestId("graph-corners")).toBeNull();
      expect(screen.queryByRole("button", { name: "Pinned views" })).toBeNull();
    }));

  it("flag on: the corners show, the Legend is gone, the stats line stays for assistive tech", () =>
    withFlag("graph-shell", true, async () => {
      render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      expect(await screen.findByTestId("graph-corners")).toBeInTheDocument();
      await waitFor(() => expect(screen.getByTestId("graph-stats")).toHaveTextContent("3 of 7 pages"));
      expect(screen.queryByRole("region", { name: "Legend" })).toBeNull();
      expect(screen.queryByRole("navigation", { name: "Graph tools" })).toBeNull();
      expect(screen.getByRole("button", { name: "Pinned views" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Think notes" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Agent chats" })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /show page types/i })).toBeInTheDocument();
    }));
});

describe("graph-shell: opening a pinned view", () => {
  const pinned: PinnedView = { id: "all-types", name: "All types", created: new Date().toISOString(), spec: { v: 1, types: "all" } };
  afterEach(() => {
    useShellStore.setState({ pendingView: null });
    vi.unstubAllGlobals();
  });

  it("flag on: a view picked in the list is applied to the graph", () =>
    withFlag("graph-shell", true, async () => {
      vi.stubGlobal("fetch", vi.fn(async (url: RequestInfo | URL) => new Response(JSON.stringify(String(url) === "/api/views" ? { views: [pinned] } : { recent: [] }), { status: 200 })));
      render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      await userEvent.click(await screen.findByRole("button", { name: "Pinned views" }));
      expect(useGraphUi.getState().shownTypes).toBeUndefined();
      await userEvent.click(await screen.findByRole("button", { name: /^All types/ }));
      expect(useGraphUi.getState().shownTypes).toBeNull();
    }));

  it("flag on: a view picked in the search panel is applied and handled", () =>
    withFlag("graph-shell", true, async () => {
      render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      await screen.findByTestId("graph-corners");
      act(() => useShellStore.getState().requestView(pinned));
      await waitFor(() => expect(useGraphUi.getState().shownTypes).toBeNull());
      expect(useShellStore.getState().pendingView).toBeNull();
    }));

  it("flag off: nothing opens it, the graph stays as it was", () =>
    withFlag("graph-shell", false, async () => {
      render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      await screen.findByRole("region", { name: "Legend" });
      act(() => useShellStore.getState().requestView(pinned));
      expect(useGraphUi.getState().shownTypes).toBeUndefined();
    }));
});
