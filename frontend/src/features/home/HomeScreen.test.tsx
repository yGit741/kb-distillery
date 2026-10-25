import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { ApiError, DataSourceProvider, type DataSource, type GraphSnapshot } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { node } from "@/features/graph/fixtures";
import { markSeen, registerTour } from "@/features/tour/tours";
import { HomeScreen, resolveConcept, type HomeHost } from "./HomeScreen";
import { ToursMenu } from "@/app/ToursMenu";
import { matchConcepts } from "./ConceptExplorer";
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

const papers = Array.from({ length: 8 }, (_, i) =>
  node(`p${i}`, { type: "paper", layer: "source", depth: "full", status: "digested", year: 2020 + i, properties: { raw: `raw/printed-docs/p${i}.pdf`, authors: "Ada Author" } } as never),
);
const snapshot = {
  generated_at: "t",
  etag: "e",
  node_count: 10,
  link_count: 10,
  nodes: [node("hub", { title: "The hub", type: "idea" }), node("q-x", { type: "question", status: "open", title: "Why?" }), ...papers],
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

  it("lists only the first-visit journey (others stay startable by ?tour=), ticks seen ones and starts one", async () => {
    registerTour("menu-demo", [{ target: "body", title: "t", body: "b" }], "A demo line");
    markSeen("first-visit");
    render(<ToursMenu />);
    await userEvent.click(screen.getByRole("button", { name: "Tours" }));
    const items = screen.getAllByRole("menuitem");
    const names = items.map((i) => i.textContent);
    expect(names.some((t) => t?.includes("first-visit"))).toBe(true);
    for (const n of ["thesis-story", "boolean-bridge"]) expect(names.some((t) => t?.includes(n))).toBe(false);
    const first = items.find((i) => i.textContent?.includes("first-visit"))!;
    expect(within(first).getByLabelText("seen")).toBeInTheDocument();
    expect(within(items.find((i) => i.textContent?.includes("A demo line"))!).queryByLabelText("seen")).toBeNull();
    await userEvent.click(items.find((i) => i.textContent?.includes("A demo line"))!);
    expect(screen.queryByRole("menu")).toBeNull();
    expect(document.querySelector('.gt-dock[aria-label="Guided tour"]')).not.toBeNull();
  });
});

const rawCard = {
  path: "raw/printed-docs/p0.pdf",
  name: "p0.pdf",
  format: "printed-docs",
  ext: "pdf",
  kind: "pdf",
  facts: { bytes: 1468006, pages: 32, added: "2026-10-22" },
  turns: [],
  has_thumb: false,
  thumb: null,
} as never;

describe("Home screen", () => {
  it("shows a loading state", () => {
    wrap(mockDataSource({ getGraph: () => new Promise(() => {}) }), <HomeScreen host={host} />);
    expect(screen.getByRole("status", { name: /loading the graph/i })).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    wrap(mockDataSource({ getGraph: async () => Promise.reject(new ApiError("boom", 500)) }), <HomeScreen host={host} />);
    expect(await screen.findByText(/could not load the graph/i)).toBeInTheDocument();
  });

  it("shows an empty state when there is no concept to pick", async () => {
    const empty = { ...snapshot, nodes: [node("a", { type: "paper", layer: "source" })], links: [] } as unknown as GraphSnapshot;
    wrap(mockDataSource({ getGraph: async () => empty }), <HomeScreen host={host} />);
    expect(await screen.findByText(/nothing to show yet/i)).toBeInTheDocument();
  });

  it("shows the title, the glossary and the picked concept with one source's pipeline", async () => {
    const getRawCard = vi.fn(async () => rawCard);
    wrap(mockDataSource({ getGraph: async () => snapshot, getPage, getRawCard }), <HomeScreen host={host} concept="hub" />);
    expect(await screen.findByRole("heading", { name: "A Map of the Knowledge That Interests Me" })).toBeInTheDocument();
    expect(screen.getByText("Created by my research agent and me.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How a page gets here" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Draw a Subgraph" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Tours" })).toBeNull(); // the menu lives in the app header
    expect(screen.getByRole("combobox", { name: "Pick a concept" })).toHaveValue("The hub");
    expect(screen.getByRole("heading", { name: "Knowledge pipeline for one source the concept relies on" })).toBeInTheDocument();
    expect(await screen.findByText("PDF · 32 pages · 1.4 MB")).toBeInTheDocument();
    expect(screen.getByText("added 2026-10-22")).toBeInTheDocument();
    expect(getRawCard).toHaveBeenCalledWith(expect.stringMatching(/^p\d$/), expect.stringMatching(/^raw\/printed-docs\/p\d\.pdf$/));
    const full = screen.getByRole("link", { name: /full graph/i });
    expect(full.getAttribute("href")).toMatch(/^\/app\/graph\?pages=/);
    await userEvent.click(full);
    expect(host.openGraph).toHaveBeenCalledWith(expect.objectContaining({ focus: "hub" }));
  });

  it("the combobox lists concepts only and picks with the keyboard", async () => {
    const setConcept = vi.fn();
    wrap(mockDataSource({ getGraph: async () => snapshot, getPage, getRawCard: async () => rawCard }), <HomeScreen host={{ ...host, setConcept }} concept="hub" />);
    const box = await screen.findByRole("combobox", { name: "Pick a concept" });
    await userEvent.clear(box);
    await userEvent.type(box, "why");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([expect.stringContaining("Why?")]);
    await userEvent.keyboard("{Enter}");
    expect(setConcept).toHaveBeenCalledWith("q-x");
  });

  it("the shuffle picks a concept and puts it in the URL", async () => {
    const setConcept = vi.fn();
    wrap(mockDataSource({ getGraph: async () => snapshot, getPage, getRawCard: async () => rawCard }), <HomeScreen host={{ ...host, setConcept }} />);
    await userEvent.click(await screen.findByRole("button", { name: /pick a concept/i }));
    expect(["hub", "q-x"]).toContain(setConcept.mock.calls.at(-1)?.[0]);
  });

  it("falls back to facts when the raw card is not shared", async () => {
    wrap(mockDataSource({ getGraph: async () => snapshot, getPage, getRawCard: async () => Promise.reject(new ApiError("not available in the shared view", 404)) }), <HomeScreen host={host} concept="hub" />);
    expect(await screen.findByText("raw/printed-docs")).toBeInTheDocument();
    expect(screen.getByText("immutable")).toBeInTheDocument();
  });

  it("resolves the URL concept only when it is pickable", () => {
    const v = indexVault(snapshot.nodes as never, snapshot.links as never);
    expect(resolveConcept(v, "q-x", 1, false)).toBe("q-x");
    expect(["hub", "q-x"]).toContain(resolveConcept(v, "p0", 1, false));
    expect(matchConcepts(snapshot.nodes as never, "p").every((n) => n.layer !== "source")).toBe(true);
  });
});
