import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes } from "../fixtures";
import { useGraphUi } from "../store";
import { useChatDock } from "../tools/chatDockStore";
import { GraphShell } from "./GraphShell";
import { looksLikeShape, useShellStore } from "./shellStore";

const SHOWN = new Set(sampleNodes.map((n) => n.type));
const byId = new Map(sampleNodes.map((n) => [n.id, n] as const));

function setup(over: Partial<DataSource> = {}) {
  const fns = { onFocus: vi.fn(), onRead: vi.fn(), onShowExact: vi.fn(), onShowMentions: vi.fn(), onFit: vi.fn(), onZoom: vi.fn(), onReheat: vi.fn(), onRefresh: vi.fn() };
  const ds = mockDataSource({
    search: async () => ({ hits: [], total: 0 }),
    listRecent: async () => ({ recent: [] }),
    listViews: async () => ({ views: [] }),
    addRecent: vi.fn(async () => ({ recent: [] })),
    ...over,
  });
  const { unmount } = render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <GraphShell nodes={sampleNodes} byId={byId} colorBy="type" shownTypes={SHOWN} {...fns} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { ds, ...fns, unmount };
}

const box = () => screen.getByRole("combobox", { name: /search the graph/i });

beforeEach(() => {
  useChatDock.setState({ open: false, question: "" });
  useShellStore.setState({ pendingShape: null, pendingView: null, notice: null, shaping: false, shape: null, undo: null, shapeError: null });
  useGraphUi.setState({ flyout: null, railOpen: false });
});

describe("opening", () => {
  it("the search line is a 24px target (ui-principles rule 25)", () => {
    setup();
    expect(box()).toHaveClass("min-h-6");
  });

  it("opens on focus and closes on Escape", async () => {
    setup();
    expect(box()).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(box());
    expect(box()).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(box()).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("opens with Cmd-K and with Ctrl-K, and takes the key from the page", async () => {
    setup();
    const pageSaw = vi.fn();
    const listener = (e: KeyboardEvent) => e.key === "k" && pageSaw();
    window.addEventListener("keydown", listener);
    await userEvent.keyboard("{Meta>}k{/Meta}");
    expect(box()).toHaveFocus();
    expect(box()).toHaveAttribute("aria-expanded", "true");
    expect(pageSaw).not.toHaveBeenCalled();
    window.removeEventListener("keydown", listener);
    await userEvent.keyboard("{Escape}");
    await userEvent.keyboard("{Control>}k{/Control}");
    expect(box()).toHaveAttribute("aria-expanded", "true");
  });

  it("gives Cmd-K back to the page once the shell is gone", async () => {
    const { unmount } = setup();
    unmount();
    const pageSaw = vi.fn();
    const listener = (e: KeyboardEvent) => e.key === "k" && pageSaw();
    window.addEventListener("keydown", listener);
    await userEvent.keyboard("{Meta>}k{/Meta}");
    window.removeEventListener("keydown", listener);
    expect(pageSaw).toHaveBeenCalledOnce();
  });

  it("leaves Space to a menu item", async () => {
    setup();
    const item = document.createElement("div");
    item.setAttribute("role", "menuitem");
    item.tabIndex = 0;
    document.body.append(item);
    item.focus();
    await userEvent.keyboard(" ");
    expect(box()).toHaveAttribute("aria-expanded", "false");
    item.remove();
  });

  it("shows the knowledge base name as the icon's tooltip (graph-intent off)", async () => {
    const { withFlag } = await import("@/flags/testing");
    await withFlag("graph-intent", false, async () => {
      setup({ getKb: async () => ({ name: "Thesis Knowledge Base", id: "thesis" }) as never });
      const icon = await screen.findByRole("button", { name: /knowledge base: thesis knowledge base/i });
      expect(icon).toHaveAttribute("title", "Thesis Knowledge Base");
    });
  });
});

describe("at rest", () => {
  it("lists recent steps newest first, and the pinned views", async () => {
    setup({
      listRecent: async () => ({
        recent: [
          { at: "2026-11-01T10:00:00Z", text: "oldest step", spec: {} },
          { at: "2026-11-02T10:00:00Z", text: "newest step", spec: {} },
        ],
      }),
      listViews: async () => ({ views: [{ id: "v1", name: "Learning theory", created: "2026-11-01", spec: {} }] }),
    });
    await userEvent.click(box());
    const opts = await screen.findAllByRole("option");
    expect(opts.map((o) => o.textContent)).toEqual(["newest step", "oldest step", "Learning theory"]);
    expect(screen.getByText("Recent")).toBeInTheDocument();
    expect(screen.getByText("Pinned views")).toBeInTheDocument();
  });

  it("a pinned view records the request for the corner controls to open, with no notice", async () => {
    setup({ listViews: async () => ({ views: [{ id: "v1", name: "Learning theory", created: "2026-11-01", spec: {} }] }) });
    await userEvent.click(box());
    await userEvent.click(await screen.findByRole("option", { name: /learning theory/i }));
    expect(useShellStore.getState().pendingView?.id).toBe("v1");
    expect(useShellStore.getState().notice).toBeNull();
  });

  it("a recent command runs again", async () => {
    const { onFit } = setup({ listRecent: async () => ({ recent: [{ at: "2026-11-02T10:00:00Z", text: "/Fit to view", spec: { command: "fit" } }] }) });
    await userEvent.click(box());
    await userEvent.click(await screen.findByRole("option", { name: "/Fit to view" }));
    expect(onFit).toHaveBeenCalledOnce();
  });
});

describe("page results", () => {
  it("lists live results while typing; Enter focuses the page, Shift+Enter reads it", async () => {
    const { onFocus, onRead } = setup();
    await userEvent.type(box(), "margin");
    expect(await screen.findByRole("option", { name: /idea margin/i })).toBeInTheDocument();
    await userEvent.keyboard("{Enter}");
    expect(onFocus).toHaveBeenCalledWith("idea-margin");
    await userEvent.type(box(), "margin");
    await screen.findByRole("option", { name: /idea margin/i });
    await userEvent.keyboard("{Shift>}{Enter}{/Shift}");
    expect(onRead).toHaveBeenCalledWith("idea-margin");
  });

  it("lists full-text hits with their snippet", async () => {
    setup({ search: async () => ({ hits: [{ id: "q-why-big-nets-work", title: "x", type: "question", score: 1, snippet: "mentions margin" }], total: 1 }) });
    await userEvent.type(box(), "margin");
    expect(await screen.findByText("mentions margin")).toBeInTheDocument();
  });

  it("offers pages mentioning the text", async () => {
    const { ds, onShowMentions } = setup();
    await userEvent.type(box(), "margin");
    await userEvent.click(await screen.findByRole("option", { name: /show pages mentioning/i }));
    expect(onShowMentions).toHaveBeenCalledWith("margin");
    await waitFor(() => expect(ds.addRecent).toHaveBeenCalledWith("Pages mentioning margin", { mention: "margin" }));
  });
});

describe("commands", () => {
  it("'/' lists the commands, filters them, and runs one", async () => {
    const { ds, onZoom } = setup();
    await userEvent.type(box(), "/");
    expect(await screen.findByRole("option", { name: /fit to view/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /^filters/i })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /layout and sync/i })).toBeInTheDocument();
    await userEvent.type(box(), "zoom in");
    expect(screen.queryByRole("option", { name: /fit to view/i })).not.toBeInTheDocument();
    await userEvent.keyboard("{Enter}");
    expect(onZoom).toHaveBeenCalledWith(1.25);
    await waitFor(() => expect(ds.addRecent).toHaveBeenCalledWith("/Zoom in", { command: "zoom-in" }));
    expect(box()).toHaveAttribute("aria-expanded", "false");
  });

  it("a panel command opens the panel in the toolbar", async () => {
    setup();
    await userEvent.type(box(), "/filters");
    await userEvent.keyboard("{Enter}");
    expect(useGraphUi.getState().flyout).toBe("filter");
  });

  it("the '/' key outside a field starts a command", async () => {
    setup();
    await userEvent.keyboard("/");
    expect(box()).toHaveFocus();
    expect(box()).toHaveValue("/");
    expect(await screen.findByRole("option", { name: /fit to view/i })).toBeInTheDocument();
  });

  it("lists the knowledge bases when kb-view is on", async () => {
    const { withFlag } = await import("@/flags/testing");
    const setParams = vi.fn();
    await withFlag("kb-view", true, async () => {
      const ds = mockDataSource({
        search: async () => ({ hits: [], total: 0 }),
        listRecent: async () => ({ recent: [] }),
        listViews: async () => ({ views: [] }),
        listKbs: async () => ({ kbs: [{ id: "thesis", name: "Thesis", active: true, root: "/x", error: null }, { id: "notes", name: "Notes", active: false, root: "/y", error: null }] }) as never,
      });
      render(
        <DataSourceProvider source={ds}>
          <QueryClientProvider client={new QueryClient()}>
            <GraphShell nodes={sampleNodes} byId={byId} colorBy="type" shownTypes={SHOWN} onShowExact={vi.fn()} onFocus={vi.fn()} onRead={vi.fn()} onShowMentions={vi.fn()} onFit={vi.fn()} onZoom={vi.fn()} onReheat={vi.fn()} onRefresh={vi.fn()} setParams={setParams} />
          </QueryClientProvider>
        </DataSourceProvider>,
      );
      await userEvent.type(box(), "/notes");
      await userEvent.click(await screen.findByRole("option", { name: /show notes only/i }));
      expect(setParams).toHaveBeenCalledWith({ kbs: "notes" });
    });
  });
});

describe("free text", () => {
  it("'Ask the agent' hands the text to the chat dock (spark-chat off; on, the left panel takes it: SparkPanel.test.tsx)", async () => {
    const { withFlag } = await import("@/flags/testing");
    await withFlag("spark-chat", false, async () => {
      const { ds } = setup();
      await userEvent.type(box(), "why do big nets work");
      const row = await screen.findByRole("option", { name: /ask the agent: why do big nets work/i });
      await userEvent.click(row);
      expect(useChatDock.getState().open).toBe(true);
      expect(useChatDock.getState().question).toBe("why do big nets work");
      expect(ds.addRecent).not.toHaveBeenCalled();
    });
  });

  it("a command ('/') never offers the ask row", async () => {
    setup();
    await userEvent.type(box(), "/fit");
    await screen.findByRole("option", { name: /fit to view/i });
    expect(screen.queryByRole("option", { name: /ask the agent/i })).not.toBeInTheDocument();
  });

  it("'Shape the graph' sends the text to the backend (the full flow is in GraphShell.shape.test)", async () => {
    const shapeGraph = vi.fn(async () => ({ columns: [], rows: [], row_count: 0, truncated: false, cypher: null, style: { hide_edge_kinds: [], hide_labels: [] }, style_text: "colour by areas", source: "cypher" as const, explanation: "", warnings: [] }));
    setup({ shapeGraph });
    await userEvent.type(box(), "colour by area");
    await userEvent.click(await screen.findByRole("option", { name: /shape the graph: colour by area/i }));
    await waitFor(() => expect(shapeGraph).toHaveBeenCalledWith("colour by area"));
  });

  it("text starting with MATCH is shaped first", async () => {
    setup();
    await userEvent.type(box(), "MATCH (n) RETURN n");
    const opts = await screen.findAllByRole("option");
    expect(opts[0]).toHaveTextContent(/shape the graph/i);
  });

  it("plain words do not offer the shape row", async () => {
    setup();
    await userEvent.type(box(), "margin");
    await screen.findByRole("option", { name: /idea margin/i });
    expect(screen.queryByRole("option", { name: /shape the graph/i })).not.toBeInTheDocument();
  });

  it("looksLikeShape", () => {
    for (const t of ["MATCH (n) RETURN n", "group by area", "Colour by theme", "color by area", "size by links", "layout rings", "hide people"]) expect(looksLikeShape(t)).toBe(true);
    for (const t of ["what is a margin", "tensor rank", "matching pages", ""]) expect(looksLikeShape(t)).toBe(false);
  });
});

describe("keyboard", () => {
  it("arrows move the highlight and wrap; the combobox points at the active option", async () => {
    setup();
    await userEvent.type(box(), "/");
    const opts = await screen.findAllByRole("option");
    expect(opts[0]).toHaveAttribute("aria-selected", "true");
    expect(box()).toHaveAttribute("aria-activedescendant", opts[0]!.id);
    await userEvent.keyboard("{ArrowDown}");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    expect(box()).toHaveAttribute("aria-activedescendant", opts[1]!.id);
    await userEvent.keyboard("{ArrowUp}{ArrowUp}");
    expect(screen.getAllByRole("option").at(-1)).toHaveAttribute("aria-selected", "true");
  });

  it("Escape clears the text and closes", async () => {
    setup();
    await userEvent.type(box(), "/fit");
    await userEvent.keyboard("{Escape}");
    expect(box()).toHaveValue("");
    expect(box()).toHaveAttribute("aria-expanded", "false");
  });

  it("a click outside closes the panel", async () => {
    setup();
    await userEvent.click(box());
    await userEvent.click(document.body);
    expect(box()).toHaveAttribute("aria-expanded", "false");
  });
});
