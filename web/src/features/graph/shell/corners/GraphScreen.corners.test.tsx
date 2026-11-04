import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { DataSourceProvider, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleSnapshot } from "../../fixtures";
import { GraphScreen, type GraphHost } from "../../GraphScreen";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { resetCorners } from "./cornersStore";

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
  it("flag off: no corners; the Toolbar and the Legend stay", () =>
    withFlag("graph-shell", false, async () => {
      render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      expect(await screen.findByRole("region", { name: "Legend" })).toBeInTheDocument();
      expect(screen.getByRole("navigation", { name: "Graph tools" })).toBeInTheDocument();
      expect(screen.queryByTestId("graph-corners")).toBeNull();
      expect(screen.queryByRole("button", { name: "Pinned views" })).toBeNull();
    }));

  it("flag on: the corners show, the Toolbar and the Legend are gone, the stats line stays for assistive tech", () =>
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
