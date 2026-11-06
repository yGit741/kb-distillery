import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { node } from "../fixtures";
import { Inspector } from "../Inspector";
import { EMPTY_STACK, evaluate } from "../layers/model";
import { planSentence } from "../layers/sentenceRun";
import { useLayers } from "../layers/store";
import { ACTION_ITEMS, visibleItems } from "../menu";
import { NodeMenu } from "../NodeMenu";
import { GraphShell } from "../shell/GraphShell";
import { PinList } from "../shell/corners/PinList";
import { useShellStore } from "../shell/shellStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { useFavorites } from "./store";

const nodes = [node("margin-theory", { title: "Margin theory" }), node("kernel", { title: "Kernel methods" }), node("other", { title: "Other page" })];
const byId = new Map(nodes.map((n) => [n.id, n] as const));
const ctx = { openReader: vi.fn(), openDetails: vi.fn(), openPage: vi.fn() };
const box = () => screen.getByRole("combobox", { name: /search the graph/i });

function shell(favs: string[]) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ slugs: favs }), { status: 200 })));
  const onFocus = vi.fn();
  const ds = mockDataSource({ listRecent: async () => ({ recent: [] }), listViews: async () => ({ views: [] }) as never });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={nodes} byId={byId} colorBy="type" shownTypes={new Set(nodes.map((n) => n.type))} onFocus={onFocus} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { onFocus };
}

beforeEach(() => {
  window.localStorage.clear();
  useFavorites.setState({ slugs: new Set(), loaded: false });
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null });
  useShellStore.setState({ notice: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
});
afterEach(() => vi.unstubAllGlobals());

describe("the favorite menu action", () => {
  it("is enabled, reads Favorite then Unfavorite, and toggles the page", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    const n = nodes[0]!;
    const open = () => render(<NodeMenu node={n} x={0} y={0} colorBy="type" ctx={ctx} items={visibleItems(n, ACTION_ITEMS)} onClose={() => {}} />);
    const first = open();
    const item = screen.getByRole("menuitem", { name: /^Favorite/ });
    expect(item).toBeEnabled();
    await userEvent.click(item);
    expect(useFavorites.getState().isFavorite("margin-theory")).toBe(true);
    first.unmount();
    open();
    expect(screen.getByRole("menuitem", { name: /^Unfavorite/ })).toBeInTheDocument();
  });
});

describe("the inspector control", () => {
  const inspect = () => render(<Inspector nodes={[nodes[0]!]} byId={byId} neighbors={new Map()} colorBy="type" revealed={new Set()} pageHref={() => "#"} onClose={() => {}} onClear={() => {}} onFocus={() => {}} onRead={() => {}} onToggleSources={() => {}} />);

  it("toggles beside the title with the flag on, and is absent with it off", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    withFlag("graph-intent", true, () => inspect());
    const btn = screen.getByRole("button", { name: "Add to favorites" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    await userEvent.click(btn);
    expect(screen.getByRole("button", { name: "Remove from favorites" })).toHaveAttribute("aria-pressed", "true");
  });

  it("flag off: unchanged", () => {
    withFlag("graph-intent", false, () => inspect());
    expect(screen.queryByRole("button", { name: /favorites/i })).toBeNull();
  });
});

describe("/favorites", () => {
  it("lists the favorites as rows and Enter focuses one", async () => {
    await withFlag("graph-intent", true, async () => {
      const { onFocus } = shell(["kernel", "margin-theory"]);
      await waitFor(() => expect(useFavorites.getState().slugs.size).toBe(2));
      await userEvent.type(box(), "/favorites");
      const rows = await screen.findAllByRole("option");
      expect(rows.map((r) => r.textContent)).toEqual([expect.stringContaining("Kernel methods"), expect.stringContaining("Margin theory")]);
      expect(rows[0]!.querySelector("[aria-label=Favorite]")).not.toBeNull();
      await userEvent.keyboard("{Enter}");
      expect(onFocus).toHaveBeenCalledWith("kernel");
    });
  });

  it("says so when there are none", async () => {
    await withFlag("graph-intent", true, async () => {
      shell([]);
      await userEvent.type(box(), "/favorites");
      expect(await screen.findByText("No favorites yet. Mark one from a page's menu.")).toBeInTheDocument();
    });
  });

  it("a search row of a favorite page carries the mark; others do not", async () => {
    await withFlag("graph-intent", true, async () => {
      shell(["kernel"]);
      await waitFor(() => expect(useFavorites.getState().slugs.size).toBe(1));
      await userEvent.type(box(), "e");
      const k = await screen.findByRole("option", { name: /Kernel methods/ });
      expect(k.querySelector("[aria-label=Favorite]")).not.toBeNull();
      expect(screen.getByRole("option", { name: /Other page/ }).querySelector("[aria-label=Favorite]")).toBeNull();
    });
  });

  it("flag off: /favorites is not special", async () => {
    await withFlag("graph-intent", false, async () => {
      shell(["kernel"]);
      await userEvent.type(box(), "/favorites");
      expect(screen.queryByRole("option", { name: /Kernel methods/ })).toBeNull();
    });
  });
});

describe("> favorites", () => {
  it("evaluates against the loaded set, and a hops-of-favorites sentence resolves", async () => {
    await withFlag("graph-intent", true, async () => {
      shell(["kernel"]);
      await waitFor(() => expect(useLayers.getState().graph?.favorites?.has("kernel")).toBe(true));
      const g = useLayers.getState().graph!;
      const fav = planSentence("favorites", nodes, {});
      expect(fav.kind).toBe("ready");
      if (fav.kind === "ready") expect([...evaluate({ ...EMPTY_STACK, layers: fav.layers }, g).nodeIds!]).toEqual(["kernel"]);
      const near = planSentence("contradictions within 2 hops of favorites", nodes, {});
      expect(near.kind).toBe("ready");
      if (near.kind === "ready") expect(evaluate({ ...EMPTY_STACK, layers: near.layers }, g).skipped.join("|")).not.toMatch(/not loaded/);
    });
  });
});

describe("the pin corner list", () => {
  const props = { open: true, views: [], recent: undefined, suggest: "x", onApply: vi.fn(), onPin: vi.fn(), onRename: vi.fn(), onRecentOpen: vi.fn(), canApply: () => true };

  it("lists the favorites by title and a click focuses; hidden when empty", async () => {
    const onFavorite = vi.fn();
    const { rerender } = render(<PinList {...props} favorites={[{ id: "kernel", title: "Kernel methods" }]} onFavorite={onFavorite} />);
    await userEvent.click(screen.getByRole("button", { name: "Favorites: Kernel methods" }));
    expect(onFavorite).toHaveBeenCalledWith("kernel");
    rerender(<PinList {...props} favorites={[]} onFavorite={onFavorite} />);
    expect(screen.queryByRole("button", { name: /^Favorites:/ })).toBeNull();
  });
});
