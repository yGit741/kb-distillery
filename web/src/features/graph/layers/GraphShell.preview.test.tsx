import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { sampleLinks, sampleNodes } from "../fixtures";
import { LINE_COPY } from "../shell/copy";
import { GraphShell } from "../shell/GraphShell";
import { useShellStore } from "../shell/shellStore";
import { DEFAULT_PREFS, useGraphUi } from "../store";
import { EMPTY_STACK, makeLayer } from "./model";
import { useLayers } from "./store";

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));
const addRecent = vi.fn(async () => ({ recent: [] }));
const listRecent = vi.fn(async () => ({ recent: [] }));

const showExact = vi.fn();

function setup(shownTypes: ReadonlySet<string> = SHOWN, sets: { drawnBase?: ReadonlySet<string>; onScreen?: ReadonlySet<string> } = {}) {
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent,
    listViews: async () => ({ views: [] }),
    addRecent,
  });
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={sampleNodes} links={sampleLinks} byId={byId} colorBy="type" shownTypes={shownTypes} drawnBase={sets.drawnBase} onScreen={sets.onScreen} onFocus={vi.fn()} onRead={vi.fn()} onShowExact={showExact} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });
const layers = () => useLayers.getState().stack.layers;

beforeEach(() => {
  window.localStorage.clear();
  addRecent.mockClear();
  showExact.mockClear();
  listRecent.mockReset();
  listRecent.mockResolvedValue({ recent: [] });
  useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], applied: null, skipped: [], graph: null, preview: null });
  useShellStore.setState({ pendingShape: null, pendingView: null, pendingOp: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ ...DEFAULT_PREFS, view: null, flyout: null, railOpen: false });
  useKb.getState().clearSelection();
});

describe("a > sentence is previewed before it applies (graph-intent)", () => {
  it("first Enter previews: the stack is untouched, the row shows the lines and the count", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}");
      const row = await screen.findByTestId("resolved-line");
      await waitFor(() => expect(row).toHaveTextContent("show nodes degree = 0"));
      expect(row).toHaveTextContent(/\d+ nodes?/);
      expect(layers()).toHaveLength(0);
      expect(useLayers.getState().preview?.ids).not.toBeNull();
      expect(useGraphUi.getState().view).toBeNull();
    });
  });

  it("the preview says how to apply it", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}");
      const row = await screen.findByTestId("resolved-line");
      await waitFor(() => expect(row).toHaveTextContent(LINE_COPY.preview.hint));
      expect(row).not.toHaveTextContent("not drawn now");
    });
  });

  it("a preview whose pages the current view hides says so (applying draws them)", async () => {
    await withFlag("graph-intent", true, async () => {
      // a view that draws no paper: the papers the sentence keeps are all off screen
      setup(new Set([...SHOWN].filter((t) => t !== "paper")));
      await userEvent.type(box(), "> papers{Enter}");
      const row = await screen.findByTestId("resolved-line");
      await waitFor(() => expect(row).toHaveTextContent("show nodes type paper"));
      expect(row).toHaveTextContent("none drawn now");
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(layers()).toHaveLength(1));
    });
  });

  it("a hide draws the screen's own pages minus the hidden ones, without selecting them", async () => {
    await withFlag("graph-intent", true, async () => {
      const shown = new Set([...SHOWN].filter((t) => t !== "paper"));
      setup(shown);
      await userEvent.type(box(), "> hide people{Enter}{Enter}");
      await waitFor(() => expect(showExact).toHaveBeenCalled());
      const [ids, opts] = showExact.mock.calls.at(-1)!;
      expect(opts).toEqual({ select: false });
      const drawn = sampleNodes.filter((n) => shown.has(n.type) && n.type !== "person").map((n) => n.id);
      expect([...(ids as string[])].sort()).toEqual(drawn.sort());
    });
  });

  it("a hide takes from the pages the screen really draws (every filter, not the type filter alone)", async () => {
    await withFlag("graph-intent", true, async () => {
      // the screen draws three pages (a legend toggle or a depth filter hid the rest)
      const base = new Set(sampleNodes.slice(0, 3).map((n) => n.id));
      const person = sampleNodes.find((n) => n.type === "person")!;
      base.add(person.id);
      setup(SHOWN, { drawnBase: base, onScreen: base });
      await userEvent.type(box(), "> hide people{Enter}");
      const row = await screen.findByTestId("resolved-line");
      await waitFor(() => expect(row).toHaveTextContent(`${base.size - 1} nodes`));
      expect(row).not.toHaveTextContent("not drawn now");
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(showExact).toHaveBeenCalled());
      expect([...(showExact.mock.calls.at(-1)![0] as string[])].sort()).toEqual([...base].filter((id) => id !== person.id).sort());
    });
  });

  it("a plain line's shape word offers view lines; a row previews its line and Enter applies it", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "orp");
      const row = await screen.findByRole("option", { name: /> only orphans/ });
      expect(screen.getByRole("option", { name: /> don't show orphans/ })).toBeInTheDocument();
      // the View rows come before the page results
      const all = screen.getAllByRole("option");
      expect(all[0]).toBe(row);
      await userEvent.click(row);
      expect(box()).toHaveValue("> only orphans");
      await waitFor(() => expect(screen.getByTestId("resolved-line")).toHaveTextContent("show nodes degree = 0"));
      expect(layers()).toHaveLength(0);
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(layers()).toHaveLength(1));
    });
  });

  it("graph-intent off: a shape word offers no view lines", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      await userEvent.type(box(), "orp");
      await screen.findByRole("combobox");
      expect(screen.queryByRole("option", { name: /> only orphans/ })).not.toBeInTheDocument();
    });
  });

  it("Esc cancels the preview and gives back the knobs a style tinted", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> colour by depth{Enter}");
      await waitFor(() => expect(useGraphUi.getState().colorBy).toBe("depth"));
      expect(layers()).toHaveLength(0);
      await userEvent.keyboard("{Escape}");
      expect(useLayers.getState().preview).toBeNull();
      expect(useGraphUi.getState().colorBy).toBe(DEFAULT_PREFS.colorBy);
      expect(layers()).toHaveLength(0);
    });
  });

  it("second Enter applies, closes, and records the step in Recent", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> colour by depth{Enter}{Enter}");
      await waitFor(() => expect(layers()).toHaveLength(1));
      expect(useLayers.getState().preview).toBeNull();
      expect(useLayers.getState().history).toHaveLength(1);
      expect(useGraphUi.getState().colorBy).toBe("depth");
      expect(box()).toHaveValue("");
      await waitFor(() => expect(addRecent).toHaveBeenCalledTimes(1));
      expect((addRecent.mock.calls[0] as unknown[])[0]).toBe("colour by depth");
    });
  });

  it("editing the resolved line applies exactly what is written", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}");
      await userEvent.click(await screen.findByTitle(LINE_COPY.preview.edit));
      const field = await screen.findByRole("textbox", { name: LINE_COPY.preview.editLabel });
      expect(field).toHaveValue("show nodes degree = 0");
      await userEvent.clear(field);
      await userEvent.type(field, "show nodes type paper{Enter}");
      await waitFor(() => expect(layers()).toHaveLength(1));
      expect(layers()[0]!.subgraph.nodes).toEqual([{ t: "type", value: "paper" }]);
      expect(layers()[0]!.text).toBe("show nodes type paper");
      expect(useLayers.getState().preview).toBeNull();
    });
  });

  it("Tab from the input opens the field", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}{Tab}");
      expect(await screen.findByRole("textbox", { name: LINE_COPY.preview.editLabel })).toBeInTheDocument();
    });
  });

  it("a line that does not parse shows its reason and applies nothing", async () => {
    await withFlag("graph-intent", true, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}");
      await userEvent.click(await screen.findByTitle(LINE_COPY.preview.edit));
      const field = await screen.findByRole("textbox", { name: LINE_COPY.preview.editLabel });
      await userEvent.clear(field);
      await userEvent.type(field, "banana{Enter}");
      expect(await screen.findByRole("alert")).toHaveTextContent("Line 1");
      expect(layers()).toHaveLength(0);
    });
  });

  it("a recorded step in Recent applies again as one undo step", async () => {
    await withFlag("graph-intent", true, async () => {
      const stack = { v: 2, layers: [makeLayer("style", "nodes", {}, "colour by depth", { style: { color: "depth" } })] };
      listRecent.mockResolvedValue({ recent: [{ at: "2026-11-06T00:00:00Z", text: "colour by depth", spec: { stack, lines: ["style nodes color by depth"] } }] } as never);
      setup();
      await userEvent.click(box());
      // the Recent row, not the "> colour by depth" line to try
      await userEvent.click(await screen.findByRole("option", { name: /^colour by depth/ }));
      await waitFor(() => expect(layers()).toHaveLength(1));
      expect(useLayers.getState().history).toHaveLength(1);
      expect(useGraphUi.getState().colorBy).toBe("depth");
    });
  });

  it("off: Enter on a > line is plain search, no preview", async () => {
    await withFlag("graph-intent", false, async () => {
      setup();
      await userEvent.type(box(), "> only orphans{Enter}");
      expect(screen.queryByTestId("resolved-line")).not.toBeInTheDocument();
      expect(useLayers.getState().preview).toBeNull();
    });
  });
});
