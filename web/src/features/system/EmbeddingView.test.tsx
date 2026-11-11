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
    { ...page("margin", "Margin"), x: 0.1, y: 0.2, cluster: 0 },
    { ...page("margin-2", "Margin again"), x: 0.15, y: 0.25, cluster: 0 },
    { ...page("ramsey", "Ramsey numbers"), x: 0.9, y: 0.8, cluster: 1 },
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

  it("lists very similar pairs with their cosine", async () => {
    open({ getEmbedding: async () => report });
    expect(await screen.findByText("0.991")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Margin again" }).length).toBeGreaterThan(0);
  });

  it("no store yet: says so and draws no map", async () => {
    open({ getEmbedding: async () => ({ ...report, built: false, ok: false, vectors: 0, cards: 0, model: null, dim: 0, k: 0, missing: [], changed: [], clusters: [], points: [], duplicates: [] }) });
    expect(await screen.findByTestId("embedding-state")).toHaveTextContent("Not built yet");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("an error offers a retry", async () => {
    open({ getEmbedding: async () => { throw new ApiError("no such route", 404); } });
    expect(await screen.findByText("Could not load the embedding report")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
