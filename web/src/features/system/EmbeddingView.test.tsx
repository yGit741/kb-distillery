import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { ApiError, type DataSource } from "@/api";
import type { EmbeddingReport } from "@/api/types";
import { mockDataSource } from "@/test/datasource";
import { clusterColor } from "@/theme/palette";

const page = (slug: string, title: string) => ({ slug, title });
const report: EmbeddingReport = {
  built: true, ok: false, line: "3 vectors for 4 cards, behind (1 changed, 1 missing)", model: "test-model", dim: 1024, cards: 4, vectors: 3,
  missing: [page("new-idea", "New idea")], changed: [page("margin", "Margin")], removed: [], duplicate_cosine: 0.97,
  duplicates: [{ a: page("margin", "Margin"), b: page("margin-2", "Margin again"), cosine: 0.991 }],
  k: 2, silhouette: 0.31,
  clusters: [
    { id: 0, size: 2, cohesion: 0.82, central: [page("margin", "Margin")] },
    { id: 1, size: 1, cohesion: 0.7, central: [page("ramsey", "Ramsey numbers")] },
  ],
  points: [
    { ...page("margin", "Margin"), x: 0.1, y: 0.2, pc: [0.1, 0.2, 1], cluster: 0 },
    { ...page("margin-2", "Margin again"), x: 0.15, y: 0.25, pc: [0.15, 0.25, 0.5], cluster: 0 },
    { ...page("ramsey", "Ramsey numbers"), x: 0.9, y: 0.8, pc: [0.9, 0.8, 0], cluster: 1 },
  ],
  spectrum: [0.5, 0.3, 0.1], effective_dim: 2.4, mean_cosine: 0.41,
  components: [
    { index: 0, variance: 0.5, cumulative: 0.5, low: [page("margin", "Margin")], high: [page("ramsey", "Ramsey numbers")] },
    { index: 1, variance: 0.3, cumulative: 0.8, low: [page("margin", "Margin")], high: [page("ramsey", "Ramsey numbers")] },
    { index: 2, variance: 0.1, cumulative: 0.9, low: [page("ramsey", "Ramsey numbers")], high: [page("margin", "Margin")] },
  ],
};

const base: Partial<DataSource> = {
  getLifecycle: () => new Promise(() => {}),
  getOps: () => new Promise(() => {}),
  getHealth: () => new Promise(() => {}),
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
};

function open(over: Partial<DataSource>) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: ["/system?tab=embedding"] }), "");
  render(<App source={mockDataSource({ ...base, ...over })} router={router} />);
  return router;
}

describe("System · Embedding", () => {
  it("is a System tab", async () => {
    open({ getEmbedding: async () => report });
    const tabs = await screen.findByRole("tablist", { name: "System sections" });
    expect(within(tabs).getByRole("tab", { name: "Embedding" })).toHaveAttribute("aria-selected", "true");
  });

  it("shows the store status, the pages behind and the rebuild command", async () => {
    open({ getEmbedding: async () => report });
    expect(await screen.findByTestId("embedding-state")).toHaveTextContent("Behind the cards");
    expect(screen.getByText("3 of 4 cards")).toBeInTheDocument();
    expect(screen.getByText("test-model")).toBeInTheDocument();
    expect(screen.getByText("pixi run vectors-build")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "New idea" })).toHaveAttribute("href", "/pages/new-idea");
  });

  it("an up-to-date store shows no rebuild command", async () => {
    open({ getEmbedding: async () => ({ ...report, ok: true, missing: [], changed: [] }) });
    expect(await screen.findByTestId("embedding-state")).toHaveTextContent("Up to date");
    expect(screen.queryByText("pixi run vectors-build")).not.toBeInTheDocument();
  });

  it("draws one dot per page in its cluster's colour, and a pinned cluster dims the others", async () => {
    open({ getEmbedding: async () => report });
    const map = await screen.findByRole("img", { name: "Map of 3 pages in 2 clusters" });
    const dots = [...map.querySelectorAll("circle")];
    expect(dots.map((d) => d.getAttribute("fill"))).toEqual([clusterColor(0), clusterColor(0), clusterColor(1)]);
    await userEvent.click(screen.getByRole("button", { name: /Cluster 2/ }));
    await userEvent.unhover(screen.getByRole("button", { name: /Cluster 2/ }));
    expect(screen.getByRole("button", { name: /Cluster 2/ })).toHaveAttribute("aria-pressed", "true");
    expect(dots.map((d) => Number(d.getAttribute("opacity")) > 0.5)).toEqual([false, false, true]);
  });

  it("Dimensions: the spectrum, the effective dimension and both ends of each component", async () => {
    open({ getEmbedding: async () => report });
    expect(await screen.findByTestId("embedding-effective-dim")).toHaveTextContent("about 2 of 1,024");
    expect(screen.getByRole("img", { name: "Variance explained by the first 3 components" })).toBeInTheDocument();
    expect(screen.getByText("90.0% of the variance")).toBeInTheDocument();
    expect(screen.getByText("Component 3")).toBeInTheDocument();
    expect(screen.getAllByText("Low end:")).toHaveLength(3);
  });

  it("the map's axes follow the picked components", async () => {
    open({ getEmbedding: async () => report });
    const map = await screen.findByRole("img", { name: "Map of 3 pages in 2 clusters" });
    const xs = () => [...map.querySelectorAll("circle")].map((d) => Number(d.getAttribute("cx")));
    const before = xs();
    expect(before[0]).toBeLessThan(before[2] as number);
    await userEvent.click(screen.getByRole("button", { name: "Show component 3 on the map" }));
    expect(xs()[0]).toBeGreaterThan(xs()[2] as number);
    expect(within(screen.getByRole("group", { name: "X axis component" })).getByRole("button", { name: "3" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(screen.getByRole("group", { name: "X axis component" })).getByRole("button", { name: "1" }));
    expect(xs()).toEqual(before);
  });

  it("no names yet: offers the run with the server's default backend and sends the picked one", async () => {
    const sent: (string | undefined)[] = [];
    const none = { state: "none", default_backend: "subscription", usd: 0, failed: 0 };
    open({
      getEmbedding: async () => ({ ...report, names: none }),
      nameEmbedding: async (backend) => {
        sent.push(backend);
        return { ...report, names: { ...none, state: "running", backend } };
      },
    });
    const bar = await screen.findByTestId("embedding-names");
    expect(within(bar).getByText(/No names yet/)).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "Subscription" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(within(bar).getByRole("button", { name: "API" }));
    await userEvent.click(within(bar).getByRole("button", { name: "Name dimensions and clusters" }));
    expect(sent).toEqual(["api"]);
    expect(await within(bar).findByText(/Naming on API/)).toBeInTheDocument();
    expect(within(bar).getByRole("button", { name: "Name dimensions and clusters" })).toBeDisabled();
  });

  it("current names label the components, the clusters and the map's axes", async () => {
    open({
      getEmbedding: async () => ({
        ...report,
        names: { state: "current", default_backend: "subscription", backend: "subscription", model: "sonnet", usd: 0.04, at: "2026-11-11T09:00:00Z", failed: 0 },
        components: report.components!.map((c, i) => (i === 0 ? { ...c, low_name: "learning theory", high_name: "combinatorics", why: "Theory of training against discrete maths." } : c)),
        clusters: report.clusters.map((c, i) => (i === 0 ? { ...c, name: "Generalization bounds", why: "Pages on margins." } : c)),
      }),
    });
    expect(await screen.findByText(/Named by sonnet on Subscription, \$0.04/)).toBeInTheDocument();
    expect(screen.getByText("Theory of training against discrete maths.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("learning theory:")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Generalization bounds/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cluster 2/ })).toBeInTheDocument();
    expect(screen.getByText(/Left to right: learning theory to combinatorics/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Name again" })).toBeEnabled();
  });

  it("stale names and a failed run say so", async () => {
    open({ getEmbedding: async () => ({ ...report, names: { state: "stale", default_backend: "api", usd: 0, failed: 0, error: "not logged in" } }) });
    const bar = await screen.findByTestId("embedding-names");
    expect(within(bar).getByText(/vectors changed since the names were made/)).toBeInTheDocument();
    expect(within(bar).getByRole("alert")).toHaveTextContent("not logged in");
    expect(within(bar).getByRole("button", { name: "API" })).toHaveAttribute("aria-pressed", "true");
  });

  it("lists very similar pairs with their cosine", async () => {
    open({ getEmbedding: async () => report });
    expect(await screen.findByText("0.991")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Margin again" }).length).toBeGreaterThan(0);
  });

  it("no store yet: says so and draws no map", async () => {
    open({ getEmbedding: async () => ({ ...report, built: false, ok: false, vectors: 0, cards: 0, model: null, dim: 0, k: 0, missing: [], changed: [], clusters: [], points: [], duplicates: [], spectrum: [], components: [] }) });
    expect(await screen.findByTestId("embedding-state")).toHaveTextContent("Not built yet");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("a store that cannot be read says why instead of a generic empty message", async () => {
    open({ getEmbedding: async () => ({ ...report, ok: false, line: "vectors.sqlite mixes models [a, b]", missing: [], changed: [], clusters: [], points: [], duplicates: [], spectrum: [], components: [] }) });
    expect((await screen.findAllByText(/mixes models/)).length).toBeGreaterThan(0);
    expect(screen.queryByText("No vectors to map yet.")).not.toBeInTheDocument();
  });

  it("an error offers a retry", async () => {
    open({ getEmbedding: async () => { throw new ApiError("no such route", 404); } });
    expect(await screen.findByText("Could not load the embedding report")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
