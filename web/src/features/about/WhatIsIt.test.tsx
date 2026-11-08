import { render, screen } from "@testing-library/react";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { DataSourceProvider, type GraphSnapshot } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { node } from "@/features/graph/fixtures";
import WhatIsIt from "./index";

vi.mock("force-graph", () => {
  const make = () => {
    const proxy: unknown = new Proxy({}, { get: (_t, name: string) => (name === "_destructor" ? () => {} : () => proxy) });
    return proxy;
  };
  return { default: () => () => make() };
});

const snapshot = {
  generated_at: "t",
  etag: "e",
  node_count: 2,
  link_count: 1,
  nodes: [node("hub", { title: "The hub", type: "idea" }), node("p0", { type: "paper", layer: "source", depth: "full", properties: { raw: "raw/printed-docs/p0.pdf" } } as never)],
  links: [{ source: "p0", target: "hub", kind: "wikilink" }],
  concept_links: [],
  facets: { types: [], maturities: [], areas: [] },
} as unknown as GraphSnapshot;

describe("What is it?", () => {
  it("is the whole map card: its title, the glossary, then Pick a Concept with Back", async () => {
    const root = createRootRoute();
    const route = createRoute({ getParentRoute: () => root, path: "/what-is-it", component: WhatIsIt });
    const router = createRouter({ routeTree: root.addChildren([route]), history: createMemoryHistory({ initialEntries: ["/what-is-it?concept=hub"] }) });
    const ds = mockDataSource({ getGraph: async () => snapshot, getPage: async () => ({ card: { id: "x" }, markdown: "# x" }) as never });
    render(
      <DataSourceProvider source={ds}>
        <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </DataSourceProvider>,
    );
    expect(await screen.findByRole("heading", { level: 1, name: "A Map of the Knowledge That Interests Me" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How a page gets here" })).toBeInTheDocument();
    expect(screen.getByText("Deep")).toBeInTheDocument();
    expect(await screen.findByRole("combobox", { name: "Pick a concept" })).toHaveValue("The hub");
    expect(screen.getByRole("button", { name: "Back to the previous concept" })).toBeDisabled();
  });
});
