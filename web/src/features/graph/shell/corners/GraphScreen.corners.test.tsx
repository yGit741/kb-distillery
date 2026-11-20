import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { DataSourceProvider, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleSnapshot } from "../../fixtures";
import { GraphScreen, resetOpenedOnConcepts, type GraphHost } from "../../GraphScreen";
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
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0 });
});

describe("graph-corners: every page load opens on Concepts by theme", () => {
  it("on: a view left from an earlier visit gives way to Concepts by theme; a link that names a view still wins", () =>
    withFlag("graph-corners", true, async () => {
      resetOpenedOnConcepts();
      useGraphUi.setState({ story: "sources", colorBy: "format" });
      const { unmount } = render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      await screen.findByTestId("graph-corners");
      expect(useGraphUi.getState().story).toBe("concepts");
      expect(useGraphUi.getState().colorBy).toBe("area");
      unmount();
      // later in the same page load the view is left alone
      useGraphUi.setState({ story: "sources", colorBy: "format" });
      render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      await screen.findByTestId("graph-corners");
      expect(useGraphUi.getState().story).toBe("sources");
    }));

  it("on: a load that opens on a named view uses up the reset, so a later bare visit keeps the view", () =>
    withFlag("graph-corners", true, async () => {
      resetOpenedOnConcepts();
      const { unmount } = render(wrap(graph(), <GraphScreen search={{ view: "sources" }} host={host} />));
      await screen.findByTestId("graph-corners");
      unmount();
      useGraphUi.setState({ story: "sources", colorBy: "format" });
      render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      await screen.findByTestId("graph-corners");
      expect(useGraphUi.getState().colorBy).toBe("format");
    }));

  it("off: the view an earlier visit left stays", () =>
    withFlag("graph-corners", false, async () => {
      resetOpenedOnConcepts();
      useGraphUi.setState({ story: "sources", colorBy: "format" });
      render(wrap(graph(), <GraphScreen search={{}} host={host} />));
      await screen.findByTestId("graph-corners");
      expect(useGraphUi.getState().colorBy).toBe("format");
    }));
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

describe("graph-corners: the intermediate layer of the knowledge base on the graph", () => {
  const artifacts = {
    nodes: [
      { id: "repo:r", type: "Repo", name: "r", repo: "r" },
      { id: "r:a", type: "Folder", name: "a", parent: "repo:r", repo: "r", path: "a" },
    ],
    links: [],
    views: [{ id: "structure", name: "Code structure", types: ["Repo", "Folder"], relations: [] }],
  };
  const cards = () => [...document.querySelectorAll<HTMLButtonElement>("[data-corners=pin-loop] [data-view]")].map((b) => b.dataset.view);

  it("on: a knowledge base picked in the header menu brings its artifact views; several on one canvas bring none", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", true, () =>
        withFlag("kb-view", true, () => withFlag("graph.artifacts", true, async () => {
          vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ views: [], recent: [] }), { status: 200 })));
          const getArtifacts = vi.fn(async (o?: { kb?: string }) => (o?.kb === "code-kb" ? artifacts : null));
          const ds = { ...mockDataSource({ getGraph: async () => sampleSnapshot(), getArtifacts: getArtifacts as never }), kind: "http" } as DataSource;
          const { unmount } = render(wrap(ds, <GraphScreen search={{ kbs: "code-kb" }} host={host} />));
          await userEvent.click(await screen.findByRole("button", { name: "Pinned views" }));
          await waitFor(() => expect(cards()).toContain("view:artifact:structure"));
          expect(getArtifacts).toHaveBeenCalledWith({ kb: "code-kb" });
          // one card per layer: the artifact views lie under Intermediate layers, and no placeholders close the loop
          expect(cards()).toContain("view:intermediate");
          expect(cards()).not.toContain("view:placeholder-v1");
          unmount();
          resetCorners();
          getArtifacts.mockClear();
          render(wrap(ds, <GraphScreen search={{ kbs: "code-kb,other" }} host={host} />));
          await userEvent.click(await screen.findByRole("button", { name: "Pinned views" }));
          await waitFor(() => expect(cards()).toContain("view:concepts"));
          expect(cards()).not.toContain("view:artifact:structure");
          expect(getArtifacts).not.toHaveBeenCalled();
          vi.unstubAllGlobals();
        })),
      ),
    ));

  it("off: the graph asks for no artifact layer and the loop is as before (placeholders V1 to V3)", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", true, () =>
        withFlag("kb-view", true, () => withFlag("graph.artifacts", false, async () => {
          vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ views: [], recent: [] }), { status: 200 })));
          const getArtifacts = vi.fn(async () => artifacts);
          const ds = { ...mockDataSource({ getGraph: async () => sampleSnapshot(), getArtifacts: getArtifacts as never }), kind: "http" } as DataSource;
          render(wrap(ds, <GraphScreen search={{ kbs: "code-kb" }} host={host} />));
          await userEvent.click(await screen.findByRole("button", { name: "Pinned views" }));
          await waitFor(() => expect(cards()).toContain("view:placeholder-v1"));
          expect(cards().some((c) => c?.startsWith("view:artifact:"))).toBe(false);
          expect(cards()).not.toContain("view:intermediate");
          expect(getArtifacts).not.toHaveBeenCalled();
          vi.unstubAllGlobals();
        })),
      ),
    ));
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
