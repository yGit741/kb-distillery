import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleLinks, sampleNodes } from "../fixtures";
import { EMPTY_STACK, makeLayer } from "../layers/model";
import { useLayers } from "../layers/store";
import { GraphShell } from "../shell/GraphShell";
import { resetCorners } from "../shell/corners/cornersStore";
import { useShellStore } from "../shell/shellStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { resetGallery, useGallery } from "./galleryStore";

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));

const hubsLayer = makeLayer("show", "nodes", { nodes: [{ t: "degree", op: ">=", n: 1 }] }, "Linked pages");
const ready = [
  { id: "hubs", name: "Hubs", description: "Pages with eight or more links.", layers: ["show nodes degree >= 8"], kit: "base" },
  { id: "orphans", name: "Orphans", description: "Pages with no links at all.", layers: ["show nodes degree = 0"], kit: "base" },
  { id: "neighborhood", name: "Neighborhood of…", description: "Pages within two links of one page.", layers: ["show nodes within 2 hops of this"], kit: "base" },
  { id: "broken", name: "Broken", description: "A line this app cannot read.", layers: ["make it pretty"], kit: "base" },
];
const pinned = [
  { id: "mine", name: "My orphans", created: "2026-11-01", spec: { v: 2, layers: [makeLayer("show", "nodes", { nodes: [{ t: "degree", op: "=", n: 0 }] }, "No links")], text: "No links" } },
  { id: "old", name: "Old pin", created: "2026-10-01", spec: { v: 1, story: "", types: "all" } },
];
const recent = Array.from({ length: 12 }, (_, i) => ({ at: `2026-11-05T10:${String(i).padStart(2, "0")}:00Z`, text: `Step ${i}`, spec: { stack: { v: 2, layers: [hubsLayer] }, lines: ["show nodes degree >= 1"] } }));

let fetchCalls: { url: string; method: string; body?: { name: string; spec: Record<string, unknown> } }[] = [];

function setup() {
  fetchCalls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      fetchCalls.push({ url: String(url), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : undefined });
      return new Response(JSON.stringify({ ok: true, view: { id: "x", name: "x", created: "", spec: {} } }), { status: 200 });
    }),
  );
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent }),
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
const card = (name: string) => screen.getByRole("article", { name });
/** open through the store, then wait for the ready views to arrive */
async function openGallery() {
  act(() => useGallery.getState().show());
  await screen.findByRole("article", { name: "Hubs" });
  return screen.getByRole("dialog");
}

beforeEach(() => {
  window.localStorage.clear();
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
  resetCorners();
  resetGallery();
});
afterEach(() => vi.unstubAllGlobals());

describe("the view gallery (graph-intent)", () => {
  it("opens from the last row of /views and from the /gallery command", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/views ");
      await userEvent.click(await screen.findByRole("option", { name: /Open gallery/ }));
      expect(await screen.findByRole("dialog", { name: "Views" })).toBeInTheDocument();
      await userEvent.keyboard("{Escape}");
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      await userEvent.click(box());
      await userEvent.type(box(), "/gallery");
      await userEvent.click(await screen.findByRole("option", { name: /^View gallery/ }));
      expect(await screen.findByRole("dialog", { name: "Views" })).toBeInTheDocument();
    });
  });

  it("lists ready, pinned and recent (the last ten) views and filters them by name and description", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      const dlg = await openGallery();
      expect(within(dlg).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(["Ready views", "Pinned", "Recent"]);
      expect(within(screen.getByRole("region", { name: "Recent" })).getAllByRole("article")).toHaveLength(10);
      expect(within(screen.getByRole("region", { name: "Recent" })).getAllByRole("article")[0]).toHaveAccessibleName("Step 11");
      await userEvent.type(screen.getByRole("textbox", { name: "Filter views" }), "no links");
      expect(screen.getAllByRole("article").map((a) => a.getAttribute("aria-label"))).toEqual(["Orphans", "My orphans"]);
      await userEvent.clear(screen.getByRole("textbox", { name: "Filter views" }));
      await userEvent.type(screen.getByRole("textbox", { name: "Filter views" }), "zzzz");
      expect(screen.getByText("No view matches.")).toBeInTheDocument();
    });
  });

  it("Apply replaces the stack, Add stacks on it, and both close the window", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await openGallery();
      await userEvent.click(within(card("Hubs")).getByRole("button", { name: "Apply Hubs" }));
      expect(useLayers.getState().stack.layers.map((l) => l.text)).toHaveLength(1);
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      await openGallery();
      await userEvent.click(within(card("Orphans")).getByRole("button", { name: "Add Orphans" }));
      expect(useLayers.getState().stack.layers).toHaveLength(2);
      expect(useShellStore.getState().notice?.text).toBe("Added Orphans to the view.");
    });
  });

  it("Pin writes the layer stack under the card's name and keeps the window open", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await openGallery();
      await userEvent.click(within(card("Hubs")).getByRole("button", { name: "Pin Hubs" }));
      await waitFor(() => expect(fetchCalls.some((c) => c.method === "POST")).toBe(true));
      const post = fetchCalls.find((c) => c.method === "POST")!;
      expect(post.url).toBe("/api/views");
      expect(post.body?.name).toBe("Hubs");
      expect(post.body?.spec).toMatchObject({ v: 2 });
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
  });

  it("a view the app cannot read has its actions off; an old pin opens through the older path", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await openGallery();
      expect(within(card("Broken")).getByRole("button", { name: "Apply Broken" })).toBeDisabled();
      expect(within(card("Broken")).getByText("Cannot run on this kb.")).toBeInTheDocument();
      await userEvent.click(within(card("Old pin")).getByRole("button", { name: "Apply Old pin" }));
      expect(useShellStore.getState().pendingView?.id).toBe("old");
    });
  });

  it("keyboard: arrows move between cards, Enter applies, Shift+Enter adds", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await openGallery();
      await userEvent.click(screen.getByRole("textbox", { name: "Filter views" }));
      await userEvent.keyboard("{ArrowDown}");
      expect(card("Hubs")).toHaveFocus();
      await userEvent.keyboard("{ArrowRight}");
      expect(card("Orphans")).toHaveFocus();
      await userEvent.keyboard("{ArrowLeft}");
      expect(card("Hubs")).toHaveFocus();
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(1));
      await openGallery();
      card("Orphans").focus();
      await userEvent.keyboard("{Shift>}{Enter}{/Shift}");
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(2));
    });
  });

  it("an anchored view uses the one page in focus", async () => {
    await withFlag("graph-intent", true, async () => {
      useKb.getState().select("idea-margin");
      setup();
      await openGallery();
      const c = card("Neighborhood of…");
      expect(within(c).getByText(/Uses/)).toBeInTheDocument();
      expect(within(c).queryByRole("textbox")).toBeNull();
      await userEvent.click(within(c).getByRole("button", { name: /^Apply/ }));
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(1));
      expect(JSON.stringify(useLayers.getState().stack.layers[0]!.subgraph)).toContain("idea-margin");
      expect(JSON.stringify(useLayers.getState().stack.layers[0]!.subgraph)).not.toContain("$focus");
    });
  });

  it("an anchored view with no focus asks for a name on its card, offers did-you-mean, and applies on Enter", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await openGallery();
      const field = within(card("Neighborhood of…")).getByRole("textbox", { name: /Page for/ });
      await userEvent.click(within(card("Neighborhood of…")).getByRole("button", { name: /^Apply/ }));
      expect(field).toHaveFocus();
      expect(useLayers.getState().stack.layers).toHaveLength(0);
      await userEvent.type(field, "paper{Enter}");
      // not an exact name: nothing applied yet, the card offers the closest pages
      expect(await within(card("Neighborhood of…")).findByText("Did you mean")).toBeInTheDocument();
      expect(useLayers.getState().stack.layers).toHaveLength(0);
      await userEvent.click(within(card("Neighborhood of…")).getByRole("button", { name: "2020 listed paper" }));
      await waitFor(() => expect(useLayers.getState().stack.layers).toHaveLength(1));
      expect(JSON.stringify(useLayers.getState().stack.layers[0]!.subgraph)).toContain("2020-listed-paper");
      // a name that is exact applies straight away
      await openGallery();
      await userEvent.type(within(card("Neighborhood of…")).getByRole("textbox", { name: /Page for/ }), "idea-margin{Enter}");
      await waitFor(() => expect(JSON.stringify(useLayers.getState().stack.layers[0]!.subgraph)).toContain("idea-margin"));
    });
  });

  it("flag off: the gallery and its command do not exist", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      await userEvent.type(box(), "/");
      await screen.findByRole("option", { name: /Fit to view/ });
      expect(screen.queryByRole("option", { name: /^View gallery/ })).toBeNull();
      act(() => useGallery.getState().show());
      expect(screen.queryByRole("dialog")).toBeNull();
    });
  });
});
