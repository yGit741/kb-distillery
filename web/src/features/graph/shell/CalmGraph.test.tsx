import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes, sampleSnapshot } from "../fixtures";
import { STORIES, storyById, storyTypes } from "../lab/views";
import { parseSchema } from "../schema";
import { useGraphUi } from "../store";
import { GraphShell } from "./GraphShell";
import { activeCard, viewCards } from "./corners/panelModel";
import { applySpec } from "./corners/viewSpec";
import { useShellStore } from "./shellStore";

const schema = parseSchema(sampleSnapshot().schema);
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));
const SHOWN = new Set(sampleNodes.map((n) => n.type));

function mount(onView = vi.fn()) {
  const ds = mockDataSource({ search: async () => ({ hits: [], total: 0 }), listRecent: async () => ({ recent: [] }), listViews: async () => ({ views: [] }) });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell
          nodes={sampleNodes}
          byId={byId}
          colorBy="type"
          shownTypes={SHOWN}
          onFocus={vi.fn()}
          onRead={vi.fn()}
          onShowExact={vi.fn()}
          onShowMentions={vi.fn()}
          onFit={vi.fn()}
          onZoom={vi.fn()}
          onReheat={vi.fn()}
          onRefresh={vi.fn()}
          views={viewCards(sampleNodes, schema)}
          onPickView={onView}
        />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return onView;
}

beforeEach(() => {
  useShellStore.setState({ pendingShape: null, pendingView: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ story: "map", flyout: null });
});

const box = () => screen.getByRole("combobox", { name: /search the graph/i });

describe("flag calm-graph on", () => {
  it("the search dropdown has no Concepts, Thesis, Gaps or Sources tabs", () =>
    withFlag("calm-graph", true, async () => {
      mount();
      await userEvent.click(box());
      expect(screen.queryByTestId("view-switcher")).not.toBeInTheDocument();
      expect(screen.queryByTestId("view-panel")).not.toBeInTheDocument();
      expect(screen.queryByRole("group", { name: "Switch view" })).not.toBeInTheDocument();
      for (const name of ["Concepts", "Thesis", "Gaps", "Sources"]) expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }));

  it("picking a view goes through its slash command", () =>
    withFlag("calm-graph", true, async () => {
      const onView = mount();
      await userEvent.click(box());
      await userEvent.keyboard("/view: sou");
      await userEvent.click(screen.getByRole("option", { name: /View: Sources/ }));
      expect(onView).toHaveBeenCalledWith(expect.objectContaining({ id: "sources", spec: { v: 1, story: "sources" } }));
    }));

  it("names the two layers by schema, never by type name, so any kit gets them", () =>
    withFlag("calm-graph", true, () => {
      const job = { types: [{ id: "role", layer: "concept" as const }, { id: "posting", layer: "source" as const }] };
      expect([...storyTypes(storyById("concepts"), job)!]).toEqual(["role"]);
      expect([...storyTypes(storyById("sources"), job)!].sort()).toEqual(["posting", "role"]);
      for (const id of ["concepts", "sources"]) expect(storyById(id)?.types).toBeUndefined();
      expect(storyById("concepts")?.lab).toMatchObject({ strategy: "count", count: 12 });
    }));

  it("a card applies its named view and hides sources until Sources", () =>
    withFlag("calm-graph", true, () => {
      const applyView = vi.fn();
      const today = new Date().toISOString();
      const cards = viewCards(sampleNodes.map((n, i) => (i === 0 ? { ...n, added: today } : n)), schema);
      applySpec(cards.find((c) => c.id === "concepts")!.spec, { applyView, showPicked: vi.fn() });
      expect(applyView).toHaveBeenCalledWith("concepts");
      expect(activeCard(cards, { story: "concepts", quick: { recent: 0 } })).toBe("concepts");
      expect(activeCard(cards, { story: "", quick: { recent: 7 } })).toBe("recent");
    }));
});

describe("flag calm-graph off", () => {
  it("the panel has no switcher and the cards keep their old specs", () =>
    withFlag("calm-graph", false, async () => {
      mount();
      await userEvent.click(box());
      expect(screen.queryByTestId("view-switcher")).not.toBeInTheDocument();
      const concepts = viewCards(sampleNodes, schema).find((c) => c.id === "concepts")!;
      expect(concepts.spec).toMatchObject({ v: 1, story: "", types: expect.any(Array) });
    }));

  it("the calm views are not offered", () =>
    withFlag("calm-graph", false, async () => {
      const { storyOffered } = await import("../lab/views");
      expect(STORIES.filter((s) => ["concepts", "sources"].includes(s.id)).map(storyOffered)).toEqual([false, false]);
    }));
});
