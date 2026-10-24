import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { ApiError, DataSourceProvider, type DataSource, type GraphSnapshot } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { node } from "@/features/graph/fixtures";
import { HomeScreen, type HomeHost } from "./HomeScreen";

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

const host: HomeHost = { openGraph: vi.fn(), graphHref: (s) => `/app/graph?${new URLSearchParams(s)}` };

function wrap(ds: DataSource, ui: ReactNode) {
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>
    </DataSourceProvider>,
  );
}

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

  it("renders curated cards first and opens a card in the full graph", async () => {
    const cards = [{ title: "Story one", pages: ["hub", "p0", "p1"], focus: "hub", caption: "why" }];
    wrap(mockDataSource({ getGraph: async () => snapshot }), <HomeScreen host={host} cards={cards} />);
    expect(await screen.findByText("Story one")).toBeInTheDocument();
    expect(screen.getByText("Explore more")).toBeInTheDocument();
    const links = screen.getAllByRole("link", { name: /open in full graph/i });
    expect(links[0]).toHaveAttribute("href", "/app/graph?pages=hub%2Cp0%2Cp1&select=hub&focus=hub");
    await userEvent.click(links[0]!);
    expect(host.openGraph).toHaveBeenCalledWith({ pages: "hub,p0,p1", select: "hub", focus: "hub" });
  });

  it("rerolls a random card on demand", async () => {
    wrap(mockDataSource({ getGraph: async () => snapshot }), <HomeScreen host={host} />);
    const again = await screen.findAllByRole("button", { name: /another/i });
    expect(again.length).toBeGreaterThan(0);
    await userEvent.click(again[0]!);
    expect(screen.getAllByRole("link", { name: /open in full graph/i }).length).toBeGreaterThan(0);
  });
});
