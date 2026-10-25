import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { ApiError, DataSourceProvider, type DataSource, type GraphSnapshot } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { node } from "@/features/graph/fixtures";
import { markSeen, registerTour } from "@/features/tour/tours";
import { drawConcept, drawSubgraph, HomeScreen, TITLE_MAX, ToursMenu, type HomeHost } from "./HomeScreen";
import "./tours";
import { indexVault } from "./samplers";

// jsdom has no canvas: stand in for force-graph with a chainable no-op instance.
vi.mock("force-graph", () => {
  const make = () => {
    const proxy: unknown = new Proxy({}, { get: (_t, name: string) => (name === "_destructor" ? () => {} : () => proxy) });
    return proxy;
  };
  return { default: () => () => make() };
});

const papers = Array.from({ length: 8 }, (_, i) => node(`p${i}`, { type: "paper", layer: "source", depth: "full", status: "digested", year: 2020 + i }));
const snapshot = {
  generated_at: "t",
  etag: "e",
  node_count: 10,
  link_count: 10,
  nodes: [node("hub", { title: "The hub" }), node("q-x", { type: "question", status: "open", title: "Why?" }), ...papers],
  links: [...papers.map((p) => ({ source: p.id, target: "hub", kind: "wikilink" })), { source: "q-x", target: "p0", kind: "wikilink" }, { source: "q-x", target: "p1", kind: "wikilink" }],
  concept_links: [],
  facets: { types: [], statuses: [], areas: [] },
} as unknown as GraphSnapshot;

const host: HomeHost = {
  openGraph: vi.fn(),
  graphHref: (s) => `/app/graph?${new URLSearchParams(s)}`,
  openPage: vi.fn(),
  pageHref: (s) => `/app/pages/${s}`,
};
const getPage = async (slug: string) => ({ card: { id: slug }, markdown: `# ${slug}\n\nOpening of ${slug}.\n\n## My notes\n\nsecret` }) as never;

function wrap(ds: DataSource, ui: ReactNode) {
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>
    </DataSourceProvider>,
  );
}

describe("Tours menu", () => {
  afterEach(() => {
    document.querySelector<HTMLButtonElement>(".gt-dock .gt-skip")?.click(); // end a running tour
    localStorage.clear();
  });

  it("lists the three journeys with summaries, ticks seen ones and starts one", async () => {
    registerTour("menu-demo", [{ target: "body", title: "t", body: "b" }], "A demo line");
    markSeen("first-visit");
    render(<ToursMenu />);
    await userEvent.click(screen.getByRole("button", { name: "Tours" }));
    const items = screen.getAllByRole("menuitem");
    const names = items.map((i) => i.textContent);
    for (const n of ["first-visit", "thesis-story", "boolean-bridge"]) expect(names.some((t) => t?.includes(n))).toBe(true);
    expect(screen.getByText("Why over-parameterized networks generalize — the question I am chasing")).toBeInTheDocument();
    const first = items.find((i) => i.textContent?.includes("first-visit"))!;
    expect(within(first).getByLabelText("seen")).toBeInTheDocument();
    expect(within(items.find((i) => i.textContent?.includes("thesis-story"))!).queryByLabelText("seen")).toBeNull();
    await userEvent.click(items.find((i) => i.textContent?.includes("A demo line"))!);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.querySelector('.gt-dock[aria-label="Guided tour"]')).not.toBeNull();
  });
});

describe("Home screen", () => {
  it("shows a loading state", () => {
    wrap(mockDataSource({ getGraph: () => new Promise(() => {}) }), <HomeScreen host={host} />);
    expect(screen.getByRole("status", { name: /loading the graph/i })).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    wrap(mockDataSource({ getGraph: async () => Promise.reject(new ApiError("boom", 500)) }), <HomeScreen host={host} />);
    expect(await screen.findByText(/could not load the graph/i)).toBeInTheDocument();
  });

  it("shows an empty state when nothing can be sampled", async () => {
    const empty = { ...snapshot, nodes: [node("a")], links: [] } as unknown as GraphSnapshot;
    wrap(mockDataSource({ getGraph: async () => empty }), <HomeScreen host={host} />);
    expect(await screen.findByText(/nothing to sample yet/i)).toBeInTheDocument();
  });

  it("draws one subgraph and opens it in the full graph", async () => {
    wrap(mockDataSource({ getGraph: async () => snapshot, getPage }), <HomeScreen host={host} />);
    const section = await screen.findByRole("region", { name: "Draw a Subgraph" });
    const link = within(section).getByRole("link", { name: /open in full graph/i });
    expect(link.getAttribute("href")).toMatch(/^\/app\/graph\?pages=/);
    await userEvent.click(link);
    expect(host.openGraph).toHaveBeenCalledWith(expect.objectContaining({ pages: expect.any(String), focus: expect.any(String) }));
  });

  it("only draws titles that fit whole", () => {
    const long = node("long", { type: "question", status: "open", title: "x".repeat(TITLE_MAX + 1) });
    const v = indexVault([long, ...papers], papers.map((p) => ({ source: p.id, target: "long" })));
    for (let seed = 1; seed < 20; seed++) {
      expect(drawConcept(v, seed)?.id).not.toBe("long");
      expect(drawSubgraph(v, [], seed)?.title.length ?? 0).toBeLessThanOrEqual(TITLE_MAX);
    }
  });

  it("rerolls a random card on demand", async () => {
    wrap(mockDataSource({ getGraph: async () => snapshot, getPage }), <HomeScreen host={host} />);
    const again = await screen.findAllByRole("button", { name: /another/i });
    expect(again.length).toBeGreaterThan(0);
    await userEvent.click(again[0]!);
    expect(screen.getAllByRole("link", { name: /open in full graph/i }).length).toBeGreaterThan(0);
  });

  it("shows the intro, both draws, and a concept with its excerpt, neighbours and links", async () => {
    wrap(mockDataSource({ getGraph: async () => snapshot, getPage }), <HomeScreen host={host} />);
    expect(await screen.findByRole("heading", { name: "Draw a Subgraph" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Draw a Concept" })).toBeInTheDocument();
    expect(screen.getByText("Concept")).toBeInTheDocument();
    expect(await screen.findByText(/^Opening of (q-x|hub)\.$/)).toBeInTheDocument();
    expect(screen.queryByText("secret")).not.toBeInTheDocument();
    expect(screen.getAllByText("Linked with").length).toBeGreaterThan(0);
    const read = screen.getAllByRole("link", { name: /read/i })[0]!;
    expect(read.getAttribute("href")).toMatch(/^\/app\/pages\//);
  });
});
