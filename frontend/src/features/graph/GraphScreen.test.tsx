import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { DataSourceProvider, type DataSource } from "@/api";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { node, sampleLinks, sampleNodes, sampleSnapshot } from "./fixtures";
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

const host: GraphHost = {
  openPage: vi.fn(),
  pageHref: (s) => `/app/pages/${s}`,
  clearParams: vi.fn(),
  setParams: vi.fn(),
  go: vi.fn(),
  href: (to, search) => `/app${to}${search ? `?${new URLSearchParams(search)}` : ""}`,
};

function wrap(ds: DataSource, ui: ReactNode) {
  return (
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>
    </DataSourceProvider>
  );
}

const withGraph = (o: Partial<DataSource> = {}) => mockDataSource({ getGraph: async () => sampleSnapshot(), ...o });

beforeEach(() => {
  localStorage.clear();
  useKb.setState({ selection: new Set() });
  useGraphUi.setState({ ...DEFAULT_PREFS, shownTypes: undefined, shownDepths: null, search: "", rules: [], typeLabels: new Set(), view: null, revealed: new Set(), flyout: null, detailsOpen: false, readerSlug: null, focusRequest: null, fitTick: 0 });
});

describe("GraphScreen states", () => {
  it("shows loading, then the graph", async () => {
    render(wrap(withGraph(), <GraphScreen search={{}} host={host} />));
    expect(screen.getByRole("status", { name: /loading graph/i })).toBeInTheDocument();
    expect(await screen.findByTestId("graph-stats")).toHaveTextContent("3 of 7 pages");
  });

  it("shows an error with retry", async () => {
    const getGraph = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValue(sampleSnapshot());
    render(wrap(withGraph({ getGraph }), <GraphScreen search={{}} host={host} />));
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not load the graph/i);
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByTestId("graph-stats")).toBeInTheDocument();
  });

  it("shows an empty state for an empty vault", async () => {
    render(wrap(withGraph({ getGraph: async () => sampleSnapshot({ nodes: [], links: [], node_count: 0 }) }), <GraphScreen search={{}} host={host} />));
    expect(await screen.findByText(/no pages yet/i)).toBeInTheDocument();
  });
});

describe("legend and filters", () => {
  it("opens on the concept layer with people off; a chip brings them in", async () => {
    render(wrap(withGraph(), <GraphScreen search={{}} host={host} />));
    const legend = await screen.findByRole("region", { name: "Legend" });
    const person = within(legend).getByRole("button", { name: /^person/i });
    expect(person).toHaveAttribute("aria-pressed", "false");
    expect(within(legend).getByRole("button", { name: /^topic/i })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(person);
    expect(await screen.findByTestId("graph-stats")).toHaveTextContent("4 of 7 pages");
  });

  it("'Sources:' shows or hides every source and collection; '+' opens the filters", async () => {
    render(wrap(withGraph(), <GraphScreen search={{}} host={host} />));
    const legend = await screen.findByRole("region", { name: "Legend" });
    await userEvent.click(within(legend).getByRole("button", { name: "Sources:" }));
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("6 of 7 pages");
    await userEvent.click(within(legend).getByRole("button", { name: "Sources:" }));
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("3 of 7 pages");
    await userEvent.click(within(legend).getByRole("button", { name: "Add a filter" }));
    expect(useGraphUi.getState().flyout).toBe("filter");
  });

  it("'Show all' and 'Concepts only' switch between the whole graph and the default", async () => {
    render(wrap(withGraph(), <GraphScreen search={{}} host={host} />));
    const legend = await screen.findByRole("region", { name: "Legend" });
    await userEvent.click(within(legend).getByRole("button", { name: "Show all" }));
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("7 of 7 pages");
    await userEvent.click(within(legend).getByRole("button", { name: "Concepts only" }));
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("3 of 7 pages");
  });

  it("the filter panel narrows by text, and Escape closes it", async () => {
    render(wrap(withGraph(), <GraphScreen search={{}} host={host} />));
    await screen.findByTestId("graph-stats");
    await userEvent.click(screen.getByRole("button", { name: /^filters/i }));
    await userEvent.type(screen.getByPlaceholderText("Slug or title…"), "margin");
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("1 of 7 pages");
    await userEvent.keyboard("{Escape}");
    await userEvent.click(document.body);
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("region", { name: "Filters" })).not.toBeInTheDocument();
  });
});

describe("search", () => {
  it("finds a page by title and asks the canvas to centre on it", async () => {
    render(wrap(withGraph({ search: async () => ({ hits: [], total: 0 }) }), <GraphScreen search={{}} host={host} />));
    const input = await screen.findByRole("combobox", { name: /search a page/i });
    await userEvent.type(input, "margin");
    expect(await screen.findByRole("option", { name: /idea margin/i })).toBeInTheDocument();
    await userEvent.keyboard("{Enter}");
    expect(useGraphUi.getState().focusRequest?.id).toBe("idea-margin");
  });

  it("'/' sends the question to the chat dock", async () => {
    render(wrap(withGraph(), <GraphScreen search={{}} host={host} />));
    const input = await screen.findByRole("combobox", { name: /search a page/i });
    await userEvent.type(input, "/what is margin");
    expect(await screen.findByText(/opens the chat/i)).toBeInTheDocument();
  });

  it("lists full-text hits that are not title matches", async () => {
    const search = vi.fn(async () => ({ hits: [{ id: "q-why-big-nets-work", title: "x", type: "question", score: 1, snippet: "mentions margin" }], total: 1 }));
    render(wrap(withGraph({ search }), <GraphScreen search={{}} host={host} />));
    await userEvent.type(await screen.findByRole("combobox", { name: /search a page/i }), "margin");
    expect(await screen.findByText("mentions margin")).toBeInTheDocument();
  });
});

describe("deep links", () => {
  it("?pages= shows those pages and their neighbours as a view and selects them", async () => {
    render(wrap(withGraph(), <GraphScreen search={{ pages: "idea-margin" }} host={host} />));
    expect(await screen.findByText(/picked page/i)).toBeInTheDocument();
    await waitFor(() => expect([...useKb.getState().selection]).toEqual(["idea-margin"]));
    // idea-margin plus its neighbours (topic, paper, listed paper), drawn past the type filter
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("4 of 7 pages");
    await userEvent.click(screen.getByRole("button", { name: /clear view/i }));
    expect(host.clearParams).toHaveBeenCalledWith(["search", "pages", "scope"]);
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("3 of 7 pages");
  });

  it("?pages=&from=home shows exactly those pages (no extra hop) and keeps the select", async () => {
    render(wrap(withGraph(), <GraphScreen search={{ pages: "idea-margin", select: "idea-margin", focus: "idea-margin", from: "home" }} host={host} />));
    expect(await screen.findByText(/picked page/i)).toBeInTheDocument();
    await waitFor(() => expect([...useKb.getState().selection]).toEqual(["idea-margin"]));
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("1 of 7 pages");
  });

  it("?search= shows the pages that mention the query", async () => {
    const search = vi.fn(async () => ({ hits: [{ id: "jane-doe", title: "Jane", type: "person", score: 1, snippet: "" }], total: 1 }));
    render(wrap(withGraph({ search }), <GraphScreen search={{ search: "jane" }} host={host} />));
    expect(await screen.findByText(/mentioning/i)).toHaveTextContent("mentioning “jane”");
    expect(search).toHaveBeenCalledWith("jane", 2000);
  });

  it("?scope= shows the scope's pages", async () => {
    const getScope = vi.fn(async () => ({ slug: "scope-x", title: "X", why: "", status: "active", rows: [], projection: { hop0: ["idea-margin"], hop1: [], covered: [], hubs: [], themes: [], uncovered: [] } }));
    render(wrap(withGraph({ getScope }), <GraphScreen search={{ scope: "scope-x" }} host={host} />));
    expect(await screen.findByText(/pages in scope-x/i)).toBeInTheDocument();
  });

  it("?focus= asks for the page to be centred; ?layer= picks a layer's types", async () => {
    render(wrap(withGraph(), <GraphScreen search={{ focus: "topic-learning-theory", layer: "collection" }} host={host} />));
    await screen.findByTestId("graph-stats");
    expect(useGraphUi.getState().shownTypes).toEqual(new Set(["book", "notebook", "course", "series", "scope"]));
    expect(useGraphUi.getState().focusRequest?.id).toBe("topic-learning-theory");
  });
});

describe("selection, details, reader, menu", () => {
  it("a selection offers Details; the inspector has collapsed neighbours and See sources", async () => {
    render(wrap(withGraph(), <GraphScreen search={{}} host={host} />));
    await screen.findByTestId("graph-stats");
    act(() => useKb.getState().setSelection(["idea-margin"]));
    await userEvent.click(await screen.findByRole("button", { name: "Details" }));
    const panel = await screen.findByRole("complementary", { name: "Selected page" });
    expect(within(panel).getByText("idea margin")).toBeInTheDocument();
    expect(panel.querySelectorAll("details")).toHaveLength(2);
    expect(panel.querySelector("details[open]")).toBeNull();
    const see = within(panel).getByRole("button", { name: /see sources \(2\)/i });
    await userEvent.click(see);
    expect(useGraphUi.getState().revealed.size).toBe(2);
    expect(within(panel).getByRole("button", { name: /hide sources \(2\)/i })).toBeInTheDocument();
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("5 of 7 pages");
  });

  it("Read opens the side reader with the page text; Esc closes it", async () => {
    const getPage = vi.fn(async () => ({ card: { title: "Idea margin", id: "idea-margin" }, markdown: "Body text", backlinks: [], broken: [], frontmatter: {}, outbound: [], path: "", suggested: [] }) as never);
    render(wrap(withGraph({ getPage }), <GraphScreen search={{}} host={host} />));
    await screen.findByTestId("graph-stats");
    act(() => useKb.getState().setSelection(["idea-margin"]));
    await userEvent.click(await screen.findByRole("button", { name: "Details" }));
    await userEvent.click(await screen.findByRole("button", { name: "Read" }));
    expect(await screen.findByTestId("md")).toHaveTextContent("Body text");
    expect(screen.getByRole("link", { name: /open full page/i })).toHaveAttribute("href", "/app/pages/idea-margin");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("complementary", { name: "Page reader" })).not.toBeInTheDocument();
  });

  it("keyboard: E opens the page, Space focuses the search", async () => {
    render(wrap(withGraph(), <GraphScreen search={{}} host={host} />));
    await screen.findByTestId("graph-stats");
    act(() => useKb.getState().setSelection(["idea-margin"]));
    await userEvent.keyboard("e");
    expect(host.openPage).toHaveBeenCalledWith("idea-margin");
    await userEvent.keyboard(" ");
    expect(screen.getByRole("combobox", { name: /search a page/i })).toHaveFocus();
  });
});

describe("views bar", () => {
  it("?view=thesis applies the Thesis story and its seed view without writing the URL back", async () => {
    vi.mocked(host.setParams).mockClear();
    // the fixture needs one page of the thesis spine for the seed view to have a hit
    const nodes = [...sampleNodes, node("theme-boolean-analysis", { inDegree: 2, outDegree: 1, areas: ["boolean-analysis"] })];
    const links = [...sampleLinks, { source: "theme-boolean-analysis", target: "idea-margin", kind: "wikilink" as const }];
    render(wrap(withGraph({ getGraph: async () => sampleSnapshot({ nodes, links, node_count: nodes.length }) }), <GraphScreen search={{ view: "thesis" }} host={host} />));
    await screen.findByTestId("graph-stats");
    await waitFor(() => expect(useGraphUi.getState().story).toBe("thesis"));
    expect(useGraphUi.getState().view?.label).toBe("Thesis");
    expect(screen.getByRole("button", { name: "Thesis" })).toHaveAttribute("aria-pressed", "true");
    expect(host.setParams).not.toHaveBeenCalled();
  });

  it("clicking the Thesis pill applies the story and puts view=thesis in the URL", async () => {
    vi.mocked(host.setParams).mockClear();
    render(wrap(withGraph(), <GraphScreen search={{}} host={host} />));
    await screen.findByTestId("graph-stats");
    expect(screen.getByRole("button", { name: "Map" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "Thesis" }));
    expect(useGraphUi.getState().story).toBe("thesis");
    expect(host.setParams).toHaveBeenCalledWith(expect.objectContaining({ view: "thesis" }));
  });
});
