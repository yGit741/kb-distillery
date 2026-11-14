import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource } from "@/api";
import { useHeaderFold } from "@/app/headerFold";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { sampleSnapshot } from "../fixtures";
import { GraphScreen, type GraphHost } from "../GraphScreen";

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

const ds = (over: Partial<DataSource> = {}): DataSource =>
  mockDataSource({ getGraph: async () => sampleSnapshot(), ...over, search: async () => ({ hits: [], total: 0 }), listRecent: async () => ({ recent: [] }), listViews: async () => ({ views: [] }) });

const screenWith = (over: Partial<DataSource> = {}) =>
  render(
    <DataSourceProvider source={ds(over)}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphScreen search={{}} host={host} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );

beforeEach(() => {
  localStorage.clear();
  useHeaderFold.setState({ folded: true, mounted: false });
});

describe("flag header-fold on the graph screen", () => {
  it("on: the chevron opens the bar and a double click on the hairline folds and unfolds it", () =>
    withFlag("graph-shell", true, () =>
      withFlag("header-fold", true, async () => {
        screenWith();
        const show = await screen.findByRole("button", { name: "Show the app bar" });
        const frame = screen.getByTestId("graph-screen");
        expect(frame.className).toContain("top-0");
        await userEvent.click(show);
        expect(frame.className).toContain("top-12");
        expect(screen.getByRole("button", { name: "Hide the app bar" })).toHaveAttribute("aria-expanded", "true");
        fireEvent.doubleClick(screen.getByTestId("header-fold"));
        expect(frame.className).toContain("top-0");
        // the same double click on the same strip brings it back
        fireEvent.doubleClick(screen.getByTestId("header-fold"));
        expect(frame.className).toContain("top-12");
      }),
    ));

  it("on: the chevron sits centred in the 14px row above the search line, not pulled up past the top edge", () =>
    withFlag("graph-shell", true, () =>
      withFlag("header-fold", true, async () => {
        screenWith();
        const btn = await screen.findByRole("button", { name: "Show the app bar" });
        // a 24px hit target centred on the 14px row (equal -my), so a second press on the same spot still lands
        expect(btn.className).toContain("h-6");
        expect(btn.className).toContain("-my-[5px]");
        expect(btn.className).toContain("items-center");
        expect(btn.className).not.toMatch(/-mt-|items-end/);
        expect(screen.getByTestId("header-fold").className).toContain("h-3.5");
      }),
    ));

  it("on: a graph that fails to load keeps the bar, since there is no chevron to bring it back", () =>
    withFlag("graph-shell", true, () =>
      withFlag("header-fold", true, async () => {
        screenWith({ getGraph: async () => { throw new Error("down"); } });
        expect(await screen.findByText(/could not load the graph/i)).toBeInTheDocument();
        expect(screen.getByTestId("graph-screen").className).toContain("top-12");
        expect(screen.queryByTestId("header-fold")).not.toBeInTheDocument();
        expect(useHeaderFold.getState().mounted).toBe(false);
      }),
    ));

  it("off: no chevron, the frame stays under the bar", () =>
    withFlag("graph-shell", true, () =>
      withFlag("header-fold", false, async () => {
        screenWith();
        const frame = await screen.findByTestId("graph-screen");
        expect(frame.className).toContain("top-12");
        expect(screen.queryByTestId("header-fold")).not.toBeInTheDocument();
      }),
    ));
});
