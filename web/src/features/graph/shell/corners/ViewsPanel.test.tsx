import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { useTheme } from "@/theme/theme";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes, sampleSnapshot } from "../../fixtures";
import { parseSchema } from "../../schema";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { useShellStore } from "../shellStore";
import { Corners } from "./Corners";
import { resetCorners } from "./cornersStore";
import { recentSources, viewCards } from "./panelModel";

const schema = parseSchema(sampleSnapshot().schema);
const visible = new Set(sampleNodes.filter((n) => ["topic", "idea", "question"].includes(n.type)).map((n) => n.id));
const today = new Date().toISOString();
const nodes = sampleNodes.map((n) => (n.id === "2019-fine-grained" ? { ...n, added: today, label: "Fine grained paper" } : n));
const host = { go: vi.fn(), href: (to: string) => to, openPage: vi.fn() };

function server(sessions: object[] = []) {
  const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
  return vi.fn(async (url: RequestInfo | URL) => {
    const u = String(url);
    if (u === "/api/views") return json({ views: [] });
    if (u === "/api/sessions") return json({ sessions });
    return json({ recent: [] });
  }) as unknown as typeof fetch;
}

function mount(f = server()) {
  return render(
    <DataSourceProvider source={mockDataSource({})}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <div style={{ position: "relative", width: 1200, height: 800 }}>
          <Corners nodes={nodes} visible={visible} schema={schema} shownTypes={new Set(schema.defaultVisible)} stats="x" host={host} applyView={vi.fn()} showPicked={vi.fn()} fetchImpl={f} />
        </div>
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  host.go.mockClear();
  host.openPage.mockClear();
  resetCorners();
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, hiddenKeys: new Set(), spotlight: null, view: null });
});

describe("view cards", () => {
  it("count the kb's own pages and leave out a view that does not fit", () => {
    const cards = viewCards(nodes, schema);
    const by = Object.fromEntries(cards.map((c) => [c.id, c.count]));
    expect(by.concepts).toMatch(/pages?$/);
    expect(by.sources).toBe("2");
    expect(by.recent).toBe("1 this week");
    expect(by.gaps).toBe("1 question");
    expect(by.thesis).toBeUndefined(); // no thesis spine pages in this kb
    expect(viewCards([], schema)).toEqual([]);
  });

  it("lists the newest source pages first", () => {
    expect(recentSources(nodes)[0]?.id).toBe("2019-fine-grained");
  });
});

describe("flag views-panel on", () => {
  it("opens the four sections above the pinned list and applies a view", () =>
    withFlag("views-panel", true, async () => {
      mount();
      await userEvent.click(screen.getByRole("button", { name: "Pinned views" }));
      const panel = screen.getByTestId("views-panel");
      for (const t of ["View", "Sources and chats", "Commands", "Settings"]) expect(within(panel).getByRole("region", { name: t })).toBeInTheDocument();
      expect(within(panel).getByRole("button", { name: /Fine grained paper/ })).toBeInTheDocument();
      expect(within(panel).getByRole("button", { name: /Citation genealogy/ })).toBeDisabled();
      await userEvent.click(within(panel).getByRole("button", { name: /^Sources/ }));
      expect(useGraphUi.getState().shownTypes).toEqual(new Set(["paper", "course"].filter((t) => schema.types.find((x) => x.id === t && x.layer === "source"))));
    }));

  it("lists the recent chats and the dark mode switch flips the theme", () =>
    withFlag("views-panel", true, async () => {
      useTheme.setState({ theme: "light" });
      mount(server([{ id: "s1", title: "Parity chat", updated: today }]));
      await userEvent.click(screen.getByRole("button", { name: "Pinned views" }));
      await waitFor(() => expect(screen.getByRole("button", { name: /Parity chat/ })).toBeInTheDocument());
      const sw = screen.getByRole("switch", { name: /Dark mode/ });
      expect(sw).toHaveAttribute("aria-checked", "false");
      await userEvent.click(sw);
      expect(useTheme.getState().theme).toBe("dark");
      useTheme.setState({ theme: "light" });
    }));

  it("the notice never overlaps the open panel: it sits to its right", () =>
    withFlag("views-panel", true, async () => {
      mount();
      await userEvent.click(screen.getByRole("button", { name: "Pinned views" }));
      // a pinned view nothing can restore raises the notice
      act(() => useShellStore.getState().requestView({ id: "x", name: "x", created: today, spec: {} }));
      const note = await screen.findByRole("status");
      expect(note).toHaveTextContent("Nothing in this view");
      expect(parseInt(note.style.left, 10)).toBeGreaterThanOrEqual(14 + 470);
    }));
});

describe("flag views-panel off", () => {
  it("keeps the plain pinned list: no panel", () =>
    withFlag("views-panel", false, async () => {
      mount();
      await userEvent.click(screen.getByRole("button", { name: "Pinned views" }));
      expect(screen.queryByTestId("views-panel")).toBeNull();
      expect(screen.getByRole("group", { name: "Pinned views" })).toBeInTheDocument();
    }));
});
