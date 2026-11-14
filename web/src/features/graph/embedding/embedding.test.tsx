import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { DataSourceProvider } from "@/api";
import type { EmbeddingReport } from "@/api/types";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { PROBLEM_HUES, TOPIC_COLORS, topicColor } from "@/theme/palette";
import { applySpec, captureSpec, recognisedV1 } from "../shell/corners/viewSpec";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { colorKey, colorOf, NONE_GREY, setTopics } from "../style";
import type { GNode } from "../types";
import { EmbeddingLayer } from "./EmbeddingLayer";
import { closeness, meaningPositions, missingPairs, orphansIn, topicIndex } from "./model";
import { applyEmbed, embedSpec, sameEmbed, useEmbedView } from "./store";

const page = (slug: string, title: string) => ({ slug, title });
const report: EmbeddingReport = {
  built: true, ok: true, line: "ok", model: "m", dim: 8, cards: 3, vectors: 3, missing: [], changed: [], removed: [], duplicate_cosine: 0.97,
  duplicates: [], k: 2, silhouette: 0.3, spectrum: [0.5, 0.3, 0.1], effective_dim: 2, mean_cosine: 0.3,
  near: [
    { a: page("margin", "Margin"), b: page("ramsey", "Ramsey numbers"), cosine: 0.91 },
    { a: page("margin", "Margin"), b: page("linked", "Linked page"), cosine: 0.88 },
    { a: page("margin", "Margin"), b: page("gone", "Not in the graph"), cosine: 0.85 },
  ],
  isolated: [{ slug: "ramsey", title: "Ramsey numbers", nearest: 0.31 }, { slug: "gone", title: "Not in the graph", nearest: 0.2 }],
  clusters: [
    { id: 0, size: 2, cohesion: 0.8, central: [], name: "Learning theory" },
    { id: 1, size: 1, cohesion: 0.7, central: [] },
  ],
  points: [
    { ...page("margin", "Margin"), x: 0, y: 0, pc: [0, 0, 1], cluster: 0 },
    { ...page("linked", "Linked page"), x: 0.5, y: 0.5, pc: [0.5, 0.5, 0.5], cluster: 0 },
    { ...page("ramsey", "Ramsey numbers"), x: 1, y: 1, pc: [1, 1, 0], cluster: 1 },
  ],
  components: [
    { index: 0, variance: 0.5, cumulative: 0.5, low: [], high: [], low_name: "proofs", high_name: "experiments" },
    { index: 1, variance: 0.3, cumulative: 0.8, low: [], high: [] },
    { index: 2, variance: 0.1, cumulative: 0.9, low: [], high: [] },
  ],
  similarity: { edges: [0, 1], counts: [3], nearest: [3], pairs: 3, pages: 3, sampled: false, percentiles: { p25: 0.19, p50: 0.32, p75: 0.5 }, nearest_percentiles: { p50: 0.68 } },
} as EmbeddingReport;

const node = (id: string): GNode => ({ id, title: id, type: "idea", layer: "concept", areas: [] }) as unknown as GNode;
const nodes = ["margin", "linked", "ramsey", "plain"].map(node);
const neighbors = new Map<string, readonly string[]>([["margin", ["linked"]], ["linked", ["margin"]]]);

beforeEach(() => {
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", colorBy: "area", view: null });
  useEmbedView.setState({ view: null, axes: [0, 1], tab: "pairs", pc: null, lens: null });
});

describe("embedding model", () => {
  it("topics: each page's cluster, named by the LLM or numbered", () => {
    const t = topicIndex(report);
    expect(t.of.get("ramsey")).toBe(1);
    expect(t.names.get(0)).toBe("Learning theory");
    expect(t.names.get(1)).toBe("Topic 2");
  });

  it("colour by topic: the cluster's hue, its name in the key, neutral without a vector", () => {
    const t = topicIndex(report);
    setTopics(t.of, t.names);
    expect(colorOf(node("ramsey"), "topic")).toBe(topicColor(1));
    expect(colorKey(node("margin"), "topic")).toBe("Learning theory");
    expect(colorOf(node("plain"), "topic")).toBe(NONE_GREY);
    expect(colorKey(node("plain"), "topic")).toBe("No vector");
    setTopics(new Map(), new Map());
  });

  it("topic colours never use red, orange or amber (kept for problems)", () => {
    for (const c of TOPIC_COLORS) {
      expect(PROBLEM_HUES).not.toContain(c.toLowerCase());
      // no hue in the red-orange-amber band (0..50 and 330..360 degrees)
      const [r, g, b] = [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16) / 255) as [number, number, number];
      const max = Math.max(r, g, b);
      const min = Math.min(r, g, b);
      const d = max - min;
      const h = d === 0 ? -1 : max === r ? (60 * ((g - b) / d) + 360) % 360 : max === g ? 60 * ((b - r) / d + 2) : 60 * ((r - g) / d + 4);
      if (h >= 0 && d > 0.15) expect(h > 50 && h < 330).toBe(true);
    }
    for (let i = 0; i < 20; i++) expect(TOPIC_COLORS).toContain(topicColor(i));
  });

  it("meaning map: pages by two components, high up; pages without a vector in a column to the right", () => {
    const pc = new Map<string, readonly number[]>([["a", [0, 1, 0.5]], ["b", [1, 0, 0.5]]]);
    const pos = meaningPositions(["a", "b", "z"], pc, [0, 1], 100);
    expect(pos.get("a")).toEqual([-100, -100]);
    expect(pos.get("b")).toEqual([100, 100]);
    expect(pos.get("z")![0]).toBeGreaterThan(100);
    expect(meaningPositions(["a", "b"], pc, [2, 0], 100).get("a")).toEqual([0, 100]);
  });

  it("missing links: close pairs not linked either way, both pages in the graph", () => {
    const known = new Set(nodes.map((n) => n.id));
    expect(missingPairs(report.near, known, neighbors).map((p) => p.b.slug)).toEqual(["ramsey"]);
    expect(orphansIn(report.isolated, known).map((o) => o.slug)).toEqual(["ramsey"]);
  });

  it("how close is close: the pair median and middle half, the nearest-neighbour median", () => {
    expect(closeness(report.similarity)).toEqual({ pairs: 0.32, low: 0.19, high: 0.5, nearest: 0.68 });
    expect(closeness(null)).toBeNull();
  });
});

describe("an embedding view pins and comes back", () => {
  const deps = () => ({ applyView: vi.fn(), showPicked: vi.fn() });

  it("round-trips the meaning map's axes, also with the layer stack (graph-intent)", () =>
    withFlag("ui.embedding-views", true, () =>
      withFlag("graph-intent", true, () => {
        expect(applyEmbed({ view: "map", axes: [2, 0] })).toBe(true);
        const spec = JSON.parse(JSON.stringify(captureSpec(useGraphUi.getState(), { layers: [{ id: "x" }] } as never)));
        expect(spec).toEqual({ v: 1, story: "", embed: { view: "map", axes: [2, 0] } });
        expect(recognisedV1(spec)).toBe(true);
        useEmbedView.setState({ view: null, axes: [0, 1] });
        useGraphUi.setState({ colorBy: "area" });
        expect(applySpec(spec, deps())).toBe(true);
        expect(useEmbedView.getState()).toMatchObject({ view: "map", axes: [2, 0] });
        expect(useGraphUi.getState().colorBy).toBe("topic");
      })));

  it("topics and missing links round-trip; the same view matches, another does not", () =>
    withFlag("ui.embedding-views", true, () => {
      for (const v of ["topics", "missing"] as const) {
        applyEmbed({ view: v });
        expect(captureSpec(useGraphUi.getState())).toEqual(embedSpec(v));
      }
      expect(sameEmbed(embedSpec("map", [0, 1]), { v: 1, embed: { view: "map" } })).toBe(true);
      expect(sameEmbed(embedSpec("map", [0, 2]), embedSpec("map", [0, 1]))).toBe(false);
      expect(sameEmbed(embedSpec("topics"), embedSpec("missing"))).toBe(false);
    }));

  it("with the flag off an embedding pin is not restored", () =>
    withFlag("ui.embedding-views", false, () => {
      expect(applySpec(embedSpec("topics"), deps())).toBe(false);
      expect(useEmbedView.getState().view).toBeNull();
      expect(useGraphUi.getState().colorBy).toBe("area");
    }));

  it("applying another view leaves the embedding view", () =>
    withFlag("ui.embedding-views", true, () => {
      applyEmbed({ view: "missing" });
      applySpec({ v: 1, colorBy: "status" }, deps());
      expect(useEmbedView.getState().view).toBeNull();
    }));
});

function mount(getEmbedding = vi.fn(async () => report)) {
  const ds = mockDataSource({ getEmbedding });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <EmbeddingLayer nodes={nodes} neighbors={neighbors} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return getEmbedding;
}

describe("the embedding layer on the graph", () => {
  it("flag off: nothing is fetched or drawn", () =>
    withFlag("ui.embedding-views", false, async () => {
      const get = mount();
      useEmbedView.setState({ view: "missing" });
      await new Promise((r) => setTimeout(r, 20));
      expect(get).not.toHaveBeenCalled();
      expect(screen.queryByTestId("missing-links")).toBeNull();
    }));

  it("meaning map: axis names and pickers, and how close is close", () =>
    withFlag("ui.embedding-views", true, async () => {
      mount();
      applyEmbed({ view: "map" });
      const card = await screen.findByTestId("meaning-card");
      expect(within(card).getByLabelText("x axis")).toHaveDisplayValue("proofs → experiments");
      await userEvent.selectOptions(within(card).getByLabelText("y axis"), "Component 3");
      expect(useEmbedView.getState().axes).toEqual([0, 2]);
      expect(within(card).getByTestId("closeness")).toHaveTextContent("median 0.32");
      await waitFor(() => expect(useEmbedView.getState().pc?.get("ramsey")).toEqual([1, 1, 0]));
    }));

  it("missing links: the lens, the ranked list, the orphans tab, and a row selects its pages", () =>
    withFlag("ui.embedding-views", true, async () => {
      mount();
      applyEmbed({ view: "missing" });
      const list = await screen.findByTestId("missing-links");
      await waitFor(() => expect(useEmbedView.getState().lens?.pairs).toHaveLength(1));
      expect([...useEmbedView.getState().lens!.pages].sort()).toEqual(["margin", "ramsey"]);
      await userEvent.click(within(list).getByRole("button", { name: /Margin.*Ramsey numbers/ }));
      expect([...useKb.getState().selection].sort()).toEqual(["margin", "ramsey"]);
      await userEvent.click(within(list).getByRole("button", { name: "Semantic orphans 1" }));
      expect(within(list).getByText("Ramsey numbers")).toBeInTheDocument();
      await userEvent.click(within(list).getByRole("button", { name: "Leave missing links" }));
      expect(useEmbedView.getState().view).toBeNull();
      expect(useEmbedView.getState().lens).toBeNull();
    }));
});
