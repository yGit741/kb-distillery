import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, createEmbeddedDataSource, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import type { ShareBlob } from "@/share/blob";
import { sampleLinks, sampleNodes } from "../fixtures";
import { EMPTY_STACK, makeLayer } from "../layers/model";
import { useLayers } from "../layers/store";
import { resetGallery, useGallery } from "../views/galleryStore";
import { useFavorites } from "../favorites/store";
import { ACTION_ITEMS, setActionItems, visibleItems } from "../menu";
import { exportPages } from "../export/runExport";
import { GraphShell } from "./GraphShell";
import { capabilities } from "./capabilities";
import { resetCorners } from "./corners/cornersStore";
import { useShellStore } from "./shellStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";

// the shared site: the build says so; the data is the baked blob, there is no server
vi.mock("@/share/env", () => ({ IS_SHARE: true, SHARE_PROFILE: "private" }));

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));
const pinnedLayer = makeLayer("show", "nodes", { nodes: [{ t: "degree", op: "=", n: 0 }] }, "No links");
const blob = {
  graph: { nodes: sampleNodes, links: sampleLinks },
  index: { pages: [] },
  pages: {},
  views: [{ id: "mine", name: "My orphans", created: "2026-11-01", spec: { v: 2, layers: [pinnedLayer], text: "No links" } }],
  readyViews: [{ id: "hubs", name: "Hubs", description: "Pages with eight or more links.", layers: ["show nodes degree >= 8"], kit: "base" }],
  favorites: [sampleNodes[0]!.id],
} as unknown as ShareBlob;

/** Every door to the server or to a model: none may be opened. */
const forbidden = () => {
  const names = ["layersFromText", "shapeGraph", "addRecent", "listRecent", "sendChatMessage", "answerChat", "chatStream", "saveChat", "captureThink", "saveThinkNote", "runCypher", "runGraphQuery"] as const;
  return Object.fromEntries(names.map((n) => [n, vi.fn(async () => ({}))])) as Record<(typeof names)[number], ReturnType<typeof vi.fn>>;
};

let spies: ReturnType<typeof forbidden>;
let fetchSpy: ReturnType<typeof vi.fn>;

function setup() {
  spies = forbidden();
  fetchSpy = vi.fn(async (_url: unknown, _init?: RequestInit) => new Response("{}", { status: 404 }));
  vi.stubGlobal("fetch", fetchSpy);
  vi.stubGlobal("KB_EMBEDDED", blob);
  const ds = { ...createEmbeddedDataSource(blob), ...spies } as unknown as DataSource;
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={sampleNodes} links={sampleLinks} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });
const noDoorOpened = () => {
  for (const [name, spy] of Object.entries(spies)) expect(spy, name).not.toHaveBeenCalled();
  const writes = fetchSpy.mock.calls.filter(([, init]) => init?.method && init.method !== "GET");
  expect(writes).toEqual([]);
};

beforeEach(() => {
  window.localStorage.clear();
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useFavorites.setState({ slugs: new Set(), loaded: false });
  useKb.getState().clearSelection();
  resetCorners();
  resetGallery();
});
afterEach(() => vi.unstubAllGlobals());

describe("the shared site, graph-intent on: what visitors can do", () => {
  it("drops the > segment from the placeholder", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      expect(box()).toHaveAttribute("placeholder", "Search everything · / commands");
    });
  });

  it("searches pages, in the browser, with no call to any server or model", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      const title = sampleNodes[0]!.title;
      await userEvent.type(box(), title.slice(0, 4));
      expect(await screen.findAllByRole("option")).not.toHaveLength(0);
      noDoorOpened();
    });
  });

  it("lists the saved and the ready views under /views and applies a saved one", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/views ");
      expect(await screen.findByRole("option", { name: /My orphans/ })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: /Hubs/ })).toBeInTheDocument();
      await userEvent.click(screen.getByRole("option", { name: /Hubs/ }));
      await waitFor(() => expect(useLayers.getState().stack.layers.length).toBeGreaterThan(0));
      noDoorOpened();
    });
  });

  it("opens the gallery with Apply and Add on every card, and no Pin", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      act(() => useGallery.getState().show());
      const hubs = await screen.findByRole("article", { name: "Hubs" });
      const dlg = screen.getByRole("dialog");
      expect(within(hubs).getByRole("button", { name: /^Apply/ })).toBeInTheDocument();
      expect(within(hubs).getByRole("button", { name: /^Add/ })).toBeInTheDocument();
      expect(within(dlg).queryByRole("button", { name: /^Pin/ })).toBeNull();
      expect(within(dlg).getByRole("article", { name: "My orphans" })).toBeInTheDocument();
      await userEvent.click(within(hubs).getByRole("button", { name: /^Apply/ }));
      noDoorOpened();
    });
  });

  it("reads the favorite marks from the page, without a request", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await waitFor(() => expect(useFavorites.getState().slugs.has(sampleNodes[0]!.id)).toBe(true));
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });
});

describe("the shared site, graph-intent on: what visitors never get", () => {
  it("shows the copy and searches instead when the line starts with >", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> colour by area");
      expect(await screen.findByText("Changing the view is not available here")).toBeInTheDocument();
      expect(screen.queryByText(/Change the view:/)).toBeNull();
      await userEvent.keyboard("{Enter}");
      noDoorOpened();
    });
  });

  it("has no Ask row and no Related-by-meaning group for typed text, and Enter calls no model", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "how does attention relate to memory");
      await waitFor(() => expect(screen.queryByText("Nothing matches.") ?? screen.queryAllByRole("option")[0]).toBeTruthy());
      expect(screen.queryByRole("option", { name: /Ask the agent/ })).toBeNull();
      expect(screen.queryByText("Related by meaning")).toBeNull();
      expect(screen.queryByRole("option", { name: /Shape the graph/ })).toBeNull();
      await userEvent.keyboard("{Enter}");
      noDoorOpened();
    });
  });

  it("has no pin, no favorite toggle, no think and no chat in the action menus", () => {
    const n = sampleNodes[0]!;
    const ids = visibleItems(n, ACTION_ITEMS).map((i) => i.id);
    expect(ids).toEqual(expect.arrayContaining(["focus", "show", "read", "expand", "export"]));
    for (const gone of ["favorite", "chat", "think"]) expect(ids).not.toContain(gone);
    const set = visibleItems(n, setActionItems([n.id], "set")).map((i) => i.id);
    for (const gone of ["chat", "think"]) expect(set).not.toContain(gone);
  });

  it("does not toggle a favorite even when asked to", async () => {
    setup();
    await useFavorites.getState().toggle("some-page");
    expect(useFavorites.getState().slugs.has("some-page")).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe("the shared site: exports and the flag off", () => {
  it("copies an OKF bundle without any `## My notes`, using the capability the shell reads", async () => {
    const write = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText: write }, configurable: true });
    const source = (slug: string) => `---\ntype: idea\n---\n\n# ${slug}\n\ntext\n\n## My notes\n\nprivate-of-${slug}\n`;
    const ds = { ...createEmbeddedDataSource(blob), getPageSource: async (slug: string) => source(slug) } as DataSource;
    await withFlag("graph-intent", true, async () => {
      await exportPages(ds, ["a", "b"], { kbName: "Demo", isShare: !capabilities().exportNotes, say: vi.fn() });
    });
    const text = (write.mock.calls[0] as unknown as [string])[0];
    expect(text).toContain("OKF bundle");
    expect(text).not.toContain("My notes");
    expect(text).not.toContain("private-of-");
  });

  it("with graph-intent off the line is the plain search it always was: no views read, no marks", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      expect(box().getAttribute("placeholder")).toMatch(/^Search /);
      expect(box().getAttribute("placeholder")).not.toMatch(/everything/);
      await userEvent.click(box());
      expect(useFavorites.getState().loaded).toBe(false);
      noDoorOpened();
    });
  });
});
