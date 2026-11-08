import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleLinks, sampleNodes } from "../fixtures";
import { resetCorners } from "../shell/corners/cornersStore";
import { GraphShell } from "../shell/GraphShell";
import { useShellStore } from "../shell/shellStore";
import { resetGallery } from "../views/galleryStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { EMPTY_STACK, makeLayer } from "./model";
import { useLayers } from "./store";

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));

const hubs = makeLayer("show", "nodes", { nodes: [{ t: "degree", op: ">=", n: 1 }] }, "Linked pages");
const recentStep = { at: "2026-11-05T10:00:00Z", text: "Linked pages", spec: { stack: { v: 2, layers: [hubs] }, lines: ["show nodes degree >= 1"] } };
const olderStep = { at: "2026-11-04T10:00:00Z", text: "Colour by type", spec: { stack: { v: 2, layers: [makeLayer("style", "nodes", {}, "Colour by type", { style: { color: "type" } })] } } };
const plainStep = { at: "2026-11-03T10:00:00Z", text: "/Fit to view", spec: { command: "fit" } };
const pinned = [
  { id: "mine", name: "My orphans", created: "2026-11-01", spec: { v: 2, layers: [makeLayer("show", "nodes", { nodes: [{ t: "degree", op: "=", n: 0 }] }, "No links")], text: "No links" } },
  { id: "old", name: "Old pin", created: "2026-10-01", spec: { v: 1, story: "", types: "all" } },
  { id: "dup", name: "Linked pages", created: "2026-10-02", spec: { v: 2, layers: [hubs], text: "x" } },
];
const ready = [
  { id: "hubs", name: "Hubs", description: "Pages with eight or more links.", layers: ["show nodes degree >= 8"], kit: "base" },
  { id: "broken", name: "Broken", description: "A line this app cannot read.", layers: ["make it pretty"], kit: "base" },
];

function setup() {
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent: [plainStep, olderStep, recentStep] }), // the server keeps oldest first
    listViews: async () => ({ views: pinned }),
    listReadyViews: async () => ({ views: ready }),
    addRecent: vi.fn(async () => ({ recent: [] })),
  });
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={sampleNodes} links={sampleLinks} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });
const labels = () => screen.getAllByRole("option").map((o) => o.textContent ?? "");

beforeEach(() => {
  window.localStorage.clear();
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
  resetCorners();
  resetGallery();
});

describe("/views (graph-intent)", () => {
  it("lists recent first (newest first, views only), then pinned, then ready; the gallery is last; duplicates drop", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/views ");
      await screen.findByRole("option", { name: /Hubs/ });
      const got = labels();
      expect(got.map((l) => l.replace(/Pages with eight or more links\.|A line this app cannot read\.|Cannot run on this kb|all views/g, ""))).toEqual(["Linked pages", "Colour by type", "My orphans", "Old pin", "Hubs", "Broken", "Open gallery…"]);
    });
  });

  it("a bare /views then Enter keeps the list; an arrow then Enter applies the row", async () => {
    await withFlag("graph-intent", true, async () => {
      const ds = setup();
      void ds;
      await userEvent.type(box(), "/views");
      await screen.findByRole("option", { name: /Hubs/ });
      await userEvent.keyboard("{Enter}");
      expect(useLayers.getState().stack.layers).toHaveLength(0);
      expect(screen.getAllByRole("option").length).toBeGreaterThan(3);
      await userEvent.keyboard("{ArrowDown}{Enter}");
      await waitFor(() => expect(useLayers.getState().stack.layers.length).toBeGreaterThan(0));
    });
  });

  it("/gallery lists the Gallery command alone", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/gallery");
      await screen.findByRole("option", { name: /View gallery/ });
      expect(labels()).toHaveLength(1);
      await userEvent.keyboard("{Enter}");
      expect(await screen.findByRole("dialog", { name: "Views" })).toBeInTheDocument();
    });
  });

  it("narrows by the typed words", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/views orph");
      await screen.findByRole("option", { name: /My orphans/ });
      expect(labels().map((l) => l.replace(/all views/, ""))).toEqual(["My orphans", "Open gallery…"]);
    });
  });

  it("Enter replaces the view, Shift+Enter adds to it", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/views hubs");
      await screen.findByRole("option", { name: /Hubs/ });
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(useLayers.getState().stack.layers.map((l) => l.kind)).toEqual(["show"]));
      await userEvent.click(box());
      await userEvent.clear(box());
      await userEvent.type(box(), "/views orph");
      await screen.findByRole("option", { name: /My orphans/ });
      await userEvent.keyboard("{Shift>}{Enter}{/Shift}");
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(2));
      await userEvent.click(box());
      await userEvent.clear(box());
      await userEvent.type(box(), "/views hubs");
      await screen.findByRole("option", { name: /Hubs/ });
      await userEvent.keyboard("{Enter}");
      // Enter replaced the show layers: one left
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(1));
    });
  });

  it("a ready view with a line the app cannot read says so and applies nothing", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/views broken");
      const row = await screen.findByRole("option", { name: /Broken/ });
      expect(row).toHaveTextContent("Cannot run on this kb");
      await userEvent.keyboard("{Enter}");
      expect(useLayers.getState().stack.layers).toHaveLength(0);
    });
  });

  it("the last row opens the gallery window", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/views ");
      await userEvent.click(await screen.findByRole("option", { name: /Open gallery/ }));
      expect(await screen.findByRole("dialog", { name: "Views" })).toBeInTheDocument();
    });
  });

  it("/ lists Views and Favorites, and choosing Views fills the line", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/");
      expect(await screen.findByRole("option", { name: /^Views/ })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /^Favorites/ })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("option", { name: /^Views/ }));
      expect(box()).toHaveValue("/views ");
    });
  });

  it("flag off: neither command is listed", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      await userEvent.type(box(), "/");
      await screen.findByRole("option", { name: /Fit to view/ });
      expect(screen.queryByRole("option", { name: /^Views/ })).not.toBeInTheDocument();
      expect(screen.queryByRole("option", { name: /^Favorites/ })).not.toBeInTheDocument();
    });
  });
});
