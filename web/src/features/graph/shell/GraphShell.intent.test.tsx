import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource, type LayersResult } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes } from "../fixtures";
import { useGraphUi } from "../store";
import { useChatDock } from "../tools/chatDockStore";
import { GraphShell } from "./GraphShell";
import { parseMode, useShellStore } from "./shellStore";

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));

function setup(over: Partial<DataSource> = {}) {
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }),
    addRecent: vi.fn(async () => ({ recent: [] })),
    ...over,
  });
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={sampleNodes} byId={byId} colorBy="type" shownTypes={SHOWN} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });

beforeEach(() => {
  window.localStorage.clear();
  useChatDock.setState({ open: false, question: "" });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ flyout: null, railOpen: false });
});

describe("parseMode", () => {
  it("reads every prefix", () => {
    expect(parseMode("colour by area")).toEqual({ mode: "search", text: "colour by area" });
    expect(parseMode("> colour by area")).toEqual({ mode: "view", op: "replace", text: "colour by area" });
    expect(parseMode(">+ size by links")).toEqual({ mode: "view", op: "stack", text: "size by links" });
    expect(parseMode(">- size")).toEqual({ mode: "view", op: "remove", text: "size" });
    expect(parseMode("/fit")).toEqual({ mode: "command", text: "fit" });
    expect(parseMode("")).toEqual({ mode: "search", text: "" });
  });
});

describe("the line, graph-intent on", () => {
  it("has no knowledge base icon and shows the three-mode placeholder", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      expect(screen.queryByRole("button", { name: /knowledge base/i })).not.toBeInTheDocument();
      expect(box()).toHaveAttribute("placeholder", "Search everything · > change the view · / commands");
    });
  });

  it("offers the closest commands and a search row for an unknown slash command", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "/zoomm");
      expect(screen.queryByText("No command matches.")).not.toBeInTheDocument();
      expect(await screen.findByText("Closest options")).toBeInTheDocument();
      const instead = screen.getByRole("option", { name: "Search for 'zoomm' instead" });
      await userEvent.click(instead);
      expect(box()).toHaveValue("zoomm");
    });
  });

  it("routes a > sentence the rules cannot read to the layers endpoint with the op, not to the shape path", async () => {
    await withFlag("graph-intent", true, async () => {
      const layersFromText = vi.fn(async () => ({ layers: [], lines: [], explanation: "", backend: "subscription", usd: 0, warnings: [] }) as LayersResult);
      setup({ layersFromText });
      const seen: (string | null)[] = [];
      const off = useShellStore.subscribe((st) => seen.push(st.pendingShape));
      await userEvent.type(box(), ">+ make it feel calmer");
      await userEvent.keyboard("{Enter}");
      off();
      expect(layersFromText).toHaveBeenCalledWith("make it feel calmer", "stack");
      expect(seen.filter(Boolean)).toEqual([]);
    });
  });

  it("shows a mode's hint the first time only", async () => {
    await withFlag("graph-intent", true, async () => {
      const first = setup();
      await userEvent.click(box());
      expect(await screen.findByTestId("line-hint")).toBeInTheDocument();
      expect(JSON.parse(window.localStorage.getItem("kb-graph-line-hints-v1") ?? "{}")).toEqual({ search: true });
      first.unmount();
      setup();
      await userEvent.click(box());
      expect(screen.queryByTestId("line-hint")).not.toBeInTheDocument();
    });
  });
});

describe("the line, graph-intent off", () => {
  it("keeps the knowledge base icon, the old placeholder and the old empty text", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      expect(await screen.findByRole("button", { name: /knowledge base/i })).toBeInTheDocument();
      expect(box().getAttribute("placeholder")).toMatch(/^Search /);
      expect(box().getAttribute("placeholder")).not.toMatch(/everything/);
      await userEvent.type(box(), "/zzzzqq");
      expect(await screen.findByText("No command matches.")).toBeInTheDocument();
      expect(screen.queryByTestId("line-hint")).not.toBeInTheDocument();
    });
  });
});
