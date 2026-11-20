import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes, sampleSnapshot } from "../../fixtures";
import { parseSchema } from "../../schema";
import { applySubject } from "../../subject";
import { assignAreaColors, colorKey, effectiveColorBy } from "../../style";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { EMPTY_STACK, makeLayer } from "../../layers/model";
import { useLayers } from "../../layers/store";
import { useFavorites } from "../../favorites/store";
import { resetGallery, useGallery } from "../../views/galleryStore";
import { useChatDock } from "../../tools/chatDockStore";
import { useSparkPanel } from "../sparkPanelStore";
import { Corners, type CornersProps } from "./Corners";
import { fanReach } from "./geometry";
import { resetCorners, useCorners } from "./cornersStore";
import { arcPlaces, loopSlots, loopSolid, LOOP_H, LOOP_TOP, LOOP_W, PinLoop, rowCount, rowPlaces, rowReach, ROW_OVERLAP, SUB_H, SUB_W } from "./PinLoop";
import { SEARCH_LINE_H, SHELL_TOP_FOLDED } from "../layout";
import { useArtifactLayer } from "../../artifacts/store";
import { useTheme } from "@/theme/theme";

const schema = parseSchema(sampleSnapshot().schema);
const visible = new Set(sampleNodes.filter((n) => ["topic", "idea", "question"].includes(n.type)).map((n) => n.id));

interface Calls {
  method: string;
  url: string;
  body?: unknown;
}
/** A tiny fake of the three lists: pinned views, recent steps, saved chats (404 unless `sessions` is given). */
function fakeServer(o: { views?: { id: string; name: string }[]; recent?: { at: string; text: string; spec: object }[]; sessions?: object[] } = {}) {
  const views = (o.views ?? []).map((v) => ({ ...v, created: new Date().toISOString(), spec: { v: 1, types: "all" } }));
  const calls: Calls[] = [];
  const f = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, url: u, body });
    const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });
    if (u === "/api/views" && method === "GET") return json({ views });
    if (u === "/api/views" && method === "POST") {
      const v = { id: String(body.name).toLowerCase().replace(/\W+/g, "-"), name: body.name, created: new Date().toISOString(), spec: body.spec };
      views.push(v);
      return json({ ok: true, view: v });
    }
    const m = /^\/api\/views\/(.+)$/.exec(u);
    if (m && method === "PATCH") {
      const v = views.find((x) => x.id === m[1]);
      if (v) v.name = body.name;
      return json({ ok: true });
    }
    if (m && method === "DELETE") {
      const i = views.findIndex((x) => x.id === m[1]);
      if (i >= 0) views.splice(i, 1);
      return json({ ok: true });
    }
    if (u === "/api/recent") return json({ recent: o.recent ?? [] });
    if (u === "/api/sessions") return o.sessions ? json({ sessions: o.sessions }) : json({ error: "not found" }, 404);
    return json({ error: "unexpected " + u }, 500);
  });
  return { f: f as unknown as typeof fetch, calls, views };
}

const host = { go: vi.fn(), href: (to: string) => to, openPage: vi.fn() };
const notes = ["a-note.md", "b-note.md", "c-note.md"].map((name, i) => ({ name, mtime: 1_700_000_000 + i * 1000, size: 10 }));

function mount(server = fakeServer(), props: Partial<CornersProps> = {}, ds: Partial<DataSource> = {}) {
  const source = mockDataSource({ listThink: async () => ({ capture_note: "inbox.md", notes }), ...ds });
  return render(
    <DataSourceProvider source={source}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <div style={{ position: "relative", width: 1200, height: 800 }}>
          <Corners
            nodes={sampleNodes}
            visible={visible}
            schema={schema}
            shownTypes={new Set(schema.defaultVisible)}
            stats="3 of 7 pages"
            host={host}
            applyView={vi.fn()}
            showPicked={vi.fn()}
            fetchImpl={server.f}
            {...props}
          />
        </div>
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  host.go.mockClear();
  resetCorners();
  useChatDock.setState({ open: false, wide: false, question: "" });
  useSparkPanel.setState({ open: false, key: 0 });
  useGraphUi.setState({ ...DEFAULT_PREFS, story: "", shownTypes: undefined, predicate: null, shownDepths: null, hiddenKeys: new Set(), spotlight: null, view: null });
});

const pins = () => screen.getByRole("button", { name: "Pinned views" });
const think = () => screen.getByRole("button", { name: "Think notes" });
const agent = () => screen.getByRole("button", { name: "Agent chats" });
const expanded = (b: HTMLElement) => b.getAttribute("aria-expanded") === "true";

describe("corner buttons", () => {
  it("every control has a name and a tooltip, in plain words", () => {
    mount();
    for (const label of ["Pinned views", "Think notes", "Agent chats"]) {
      const b = screen.getByRole("button", { name: label });
      expect(b).toHaveAttribute("title", label);
    }
    expect(screen.getByRole("button", { name: /show colour names/i })).toHaveAttribute("title");
    expect(screen.getByRole("button", { name: /show page types/i })).toHaveAttribute("title");
  });

  it("the Think corner wears the drawn brain mark, the same size and line weight as its neighbours", () => {
    mount();
    const mark = think().querySelector("svg")!;
    expect(mark).toHaveAttribute("data-icon", "think");
    expect(mark).toHaveAttribute("aria-hidden", "true");
    expect(mark).toHaveAttribute("viewBox", "0 0 24 24");
    expect(mark).toHaveAttribute("fill", "none");
    expect(mark).toHaveAttribute("stroke", "currentColor");
    expect(mark).toHaveAttribute("stroke-width", "1.75");
    expect(mark).toHaveAttribute("width", "22");
    expect(mark.querySelectorAll("path")).toHaveLength(4);
    const sparkles = agent().querySelector("svg")!;
    expect(sparkles.getAttribute("stroke-width")).toBe(mark.getAttribute("stroke-width"));
    expect(sparkles.getAttribute("class")).toContain("size-[22px]");
    expect(think().querySelector(".lucide-brain")).toBeNull();
  });

  it("without a local server (a snapshot) only the legends remain", () => {
    mount(fakeServer(), {}, { kind: "embedded" });
    expect(screen.queryByRole("button", { name: "Pinned views" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Think notes" })).toBeNull();
    expect(screen.getByRole("button", { name: /show page types/i })).toBeInTheDocument();
  });
});

describe("pinned views", () => {
  // the floating list and the views panel stay behind flag pin-fan off; the fan has its own tests
  const itList = (name: string, fn: () => unknown) => it(name, () => withFlag("pin-fan", false, fn as () => Promise<void>));
  itList("lists the pinned views, newest data from GET /api/views, and applies one through the spec", async () => {
    const applyView = vi.fn();
    mount(fakeServer({ views: [{ id: "alpha", name: "Alpha view" }, { id: "beta", name: "Beta view" }] }), { applyView });
    await userEvent.click(pins());
    const alpha = await screen.findByRole("button", { name: /^Alpha view/ });
    expect(screen.getByRole("button", { name: /^Beta view/ })).toBeInTheDocument();
    await userEvent.click(alpha);
    expect(alpha).toHaveAttribute("aria-pressed", "true");
    expect(useGraphUi.getState().shownTypes).toBeNull(); // the spec said "all types"
  });

  itList("pins the current view with a name typed inline (POST /api/views {name, spec})", async () => {
    const server = fakeServer({ views: [{ id: "alpha", name: "Alpha view" }] });
    useGraphUi.setState({ colorBy: "depth" });
    mount(server);
    await userEvent.click(pins());
    await userEvent.click(await screen.findByRole("button", { name: "Pin this view" }));
    const input = screen.getByRole("textbox", { name: /name for the pinned view/i });
    await userEvent.clear(input);
    await userEvent.type(input, "My dive{Enter}");
    await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
    const post = server.calls.find((c) => c.method === "POST")!;
    expect(post.body).toMatchObject({ name: "My dive", spec: { v: 1, colorBy: "depth" } });
    expect(await screen.findByRole("button", { name: /^My dive/ })).toBeInTheDocument();
  });

  itList("graph-intent on: pinning writes the layer stack { v: 2, layers, text }; with no layers it still writes V1", async () => {
    await withFlag("graph-intent", true, async () => {
      const server = fakeServer();
      useLayers.setState({ stack: { v: 2, layers: [makeLayer("show", "nodes", { nodes: [{ t: "degree", op: ">=", n: 8 }] }, "Hubs")] } });
      mount(server);
      await userEvent.click(pins());
      await userEvent.click(await screen.findByRole("button", { name: "Pin this view" }));
      const input = screen.getByRole("textbox", { name: /name for the pinned view/i });
      await userEvent.clear(input);
      await userEvent.type(input, "Stack{Enter}");
      await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
      expect(server.calls.find((c) => c.method === "POST")!.body).toMatchObject({ name: "Stack", spec: { v: 2, text: "Hubs", layers: [{ kind: "show", text: "Hubs" }] } });
    });
    useLayers.setState({ stack: EMPTY_STACK });
  });

  itList("graph-intent on: a pinned V1 view is applied through the layer stack as one chip named like the pin", async () => {
    await withFlag("graph-intent", true, async () => {
      const applyLegacy = vi.fn();
      useLayers.setState({ stack: EMPTY_STACK, history: [], future: [], graph: { nodes: [], links: [], show: vi.fn(), applyLegacy } });
      mount(fakeServer({ views: [{ id: "alpha", name: "Alpha view" }] }));
      await userEvent.click(pins());
      await userEvent.click(await screen.findByRole("button", { name: /^Alpha view/ }));
      expect(useLayers.getState().stack.layers.map((l) => l.text)).toEqual(["Alpha view"]);
      expect(applyLegacy).toHaveBeenCalled();
    });
    useLayers.setState({ stack: EMPTY_STACK, graph: null });
  });

  itList("graph-intent on: the list holds the pinned views, favorites, Pin this view, Recent and All views; All views opens the gallery", async () => {
    await withFlag("graph-intent", true, async () => {
      useFavorites.setState({ slugs: new Set(["idea-margin"]) });
      resetGallery();
      mount(fakeServer({ views: [{ id: "alpha", name: "Alpha view" }] }));
      await userEvent.click(pins());
      await screen.findByRole("button", { name: /^Alpha view/ });
      const rows = [...document.querySelectorAll("[data-lens-row]")].filter((r) => r.getAttribute("data-lens-row") !== "div").map((r) => r.getAttribute("aria-label"));
      expect(rows).toEqual(["Alpha view, just now", "Pin this view", "Favorites: idea margin", "Show recent steps", "All views\u2026"]);
      await userEvent.click(screen.getByRole("button", { name: "All views\u2026" }));
      expect(useGallery.getState().open).toBe(true);
      expect(useCorners.getState().has("pins")).toBe(false);
    });
    resetGallery();
    useFavorites.setState({ slugs: new Set() });
  });

  itList("graph-intent off: no All views entry", async () => {
    await withFlag("graph-intent", false, async () => {
      mount(fakeServer());
      await userEvent.click(pins());
      await screen.findByRole("button", { name: "Pin this view" });
      expect(screen.queryByRole("button", { name: /All views/ })).toBeNull();
    });
  });

  itList("zero pins: only the plus card, the divider and Recent", async () => {
    mount(fakeServer());
    await userEvent.click(pins());
    await screen.findByRole("button", { name: "Pin this view" });
    expect(document.querySelectorAll("[data-lens-row=pin]")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Show recent steps" })).toBeInTheDocument();
  });

  itList("40 pins and very long names stay in one scrolling list, a name is cut with an ellipsis, not wrapped", async () => {
    const many = Array.from({ length: 40 }, (_, i) => ({ id: `v${i}`, name: i === 0 ? "A very long pinned view name ".repeat(6) : `View ${i}` }));
    mount(fakeServer({ views: many }));
    await userEvent.click(pins());
    await screen.findByRole("button", { name: /^View 39/ });
    expect(document.querySelectorAll("[data-lens-row=pin]")).toHaveLength(40);
    const long = document.querySelector("[data-lens-row=pin] span.truncate") as HTMLElement;
    expect(long.className).toContain("truncate");
    expect(long.className).toContain("max-w-[120px]");
  });

  itList("the lens grows the hovered row and less its neighbours, and lets go when the pointer leaves", async () => {
    mount(fakeServer({ views: [1, 2, 3, 4].map((i) => ({ id: `v${i}`, name: `View ${i}` })) }));
    await userEvent.click(pins());
    await screen.findByRole("button", { name: /^View 4/ });
    const row = (n: number) => screen.getByRole("button", { name: new RegExp(`^View ${n}`) });
    fireEvent(row(2), new MouseEvent("pointermove", { bubbles: true, clientY: 44 + 22 }));
    await waitFor(() => expect(Number(row(2).dataset.scale)).toBeGreaterThan(1.4), { timeout: 3000 });
    expect(Number(row(3).dataset.scale)).toBeGreaterThan(1);
    expect(Number(row(3).dataset.scale)).toBeLessThan(Number(row(2).dataset.scale));
    // the pointer is somewhere else: released
    fireEvent(document.body, new MouseEvent("pointermove", { bubbles: true, clientY: 500 }));
    await waitFor(() => expect(Number(row(2).dataset.scale)).toBeLessThan(1.05), { timeout: 3000 });
  });

  itList("'...' renames the opened view and unpins it (PATCH, DELETE)", async () => {
    const server = fakeServer({ views: [{ id: "alpha", name: "Alpha view" }] });
    mount(server);
    await userEvent.click(pins());
    await userEvent.click(await screen.findByRole("button", { name: /^Alpha view/ }));
    await userEvent.click(screen.getByRole("button", { name: "Pinned view options" }));
    await userEvent.click(screen.getByRole("button", { name: "Rename" }));
    const input = screen.getByRole("textbox", { name: /new name/i });
    await userEvent.clear(input);
    await userEvent.type(input, "Renamed{Enter}");
    await waitFor(() => expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ name: "Renamed" }));
    await userEvent.click(screen.getByRole("button", { name: "Pinned view options" }));
    await userEvent.click(screen.getByRole("button", { name: "Unpin" }));
    await waitFor(() => expect(server.calls.some((c) => c.method === "DELETE" && c.url === "/api/views/alpha")).toBe(true));
  });

  itList("Recent unfolds the last steps, newest first", async () => {
    const recent = [
      { at: "2026-11-01T10:00:00Z", text: "Oldest step", spec: { v: 1, types: "all" } },
      { at: "2026-11-02T10:00:00Z", text: "Newest step", spec: { v: 1, types: "all" } },
    ];
    mount(fakeServer({ recent }));
    await userEvent.click(pins());
    await userEvent.click(await screen.findByRole("button", { name: "Show recent steps" }));
    await screen.findByRole("button", { name: /^Newest step/ });
    const names = [...document.querySelectorAll("[data-lens-row=step]")].map((e) => e.getAttribute("aria-label"));
    expect(names[0]).toMatch(/^Newest step/);
    expect(names[1]).toMatch(/^Oldest step/);
  });
});

describe("open and close rules", () => {
  it("the pinned list closes both fans, a fan closes the list, the two fans may be open together", async () => {
    mount();
    await userEvent.click(think());
    await userEvent.click(agent());
    expect(expanded(think()) && expanded(agent())).toBe(true);
    await userEvent.click(pins());
    expect(expanded(pins())).toBe(true);
    expect(expanded(think()) || expanded(agent())).toBe(false);
    await userEvent.click(think());
    expect(expanded(think())).toBe(true);
    expect(expanded(pins())).toBe(false);
    await userEvent.click(agent());
    expect(expanded(think()) && expanded(agent())).toBe(true);
  });

  it("Escape closes the topmost layer first, then the next", async () => {
    mount();
    await userEvent.click(think());
    await userEvent.click(agent());
    await userEvent.keyboard("{Escape}");
    expect(expanded(agent())).toBe(false);
    expect(expanded(think())).toBe(true);
    await userEvent.keyboard("{Escape}");
    expect(expanded(think())).toBe(false);
  });

  it("Escape also closes a menu before its fan, and does not reach the screen's own Escape", async () => {
    const screenEsc = vi.fn();
    window.addEventListener("keydown", screenEsc);
    mount();
    await userEvent.click(agent());
    await userEvent.click(screen.getByRole("button", { name: "Agent options" }));
    expect(screen.getByRole("group", { name: "Agent options" })).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("group", { name: "Agent options" })).toBeNull();
    expect(expanded(agent())).toBe(true);
    await userEvent.keyboard("{Escape}");
    expect(expanded(agent())).toBe(false);
    expect(screenEsc).not.toHaveBeenCalled();
    await userEvent.keyboard("{Escape}"); // nothing open: the screen gets it
    expect(screenEsc).toHaveBeenCalled();
    window.removeEventListener("keydown", screenEsc);
  });

  it("a click outside closes everything", async () => {
    mount();
    await userEvent.click(think());
    await userEvent.click(agent());
    await userEvent.click(document.body);
    expect(expanded(think()) || expanded(agent())).toBe(false);
  });
});

describe("Think and Agent fans", () => {
  it("Think lists the notes newest first; a click opens the note like the Think screen", async () => {
    mount();
    await userEvent.click(think());
    const group = screen.getByRole("group", { name: "Think notes", hidden: false });
    const first = await within(group).findByRole("button", { name: /c-note/ });
    expect(within(group).getAllByRole("button")[0]).toBe(first);
    await userEvent.click(first);
    expect(host.go).toHaveBeenCalledWith("/think", { note: "c-note.md" });
    expect(expanded(think())).toBe(false);
  });

  it("Agent falls back to the browser's chat when the server has no sessions (404), and resumes it in the dock (flag spark-chat off)", async () => {
    await withFlag("spark-chat", false, async () => {
    sessionStorage.setItem("kbchat.chat", JSON.stringify({ id: "kb-chat:1", session: null, messages: [{ role: "user", content: "Is parity hard?", sources: [] }, { role: "assistant", content: "Yes." }] }));
    mount();
    await userEvent.click(agent());
    const card = await screen.findByRole("button", { name: /Is parity hard/ });
    await userEvent.click(card);
    expect(useChatDock.getState().open).toBe(true);
    });
  });

  it("flag spark-chat on: a chat opens the left panel, not the right dock", async () => {
    await withFlag("spark-chat", true, async () => {
    sessionStorage.setItem("kbchat.chat", JSON.stringify({ id: "kb-chat:1", session: null, messages: [{ role: "user", content: "Is parity hard?", sources: [] }, { role: "assistant", content: "Yes." }] }));
    mount();
    await userEvent.click(agent());
    await userEvent.click(await screen.findByRole("button", { name: /Is parity hard/ }));
    expect(useSparkPanel.getState().open).toBe(true);
    expect(useChatDock.getState().open).toBe(false);
    });
  });

  it("Agent lists the server's sessions when /api/sessions exists, and resumes one by loading its document", async () => {
    await withFlag("spark-chat", false, async () => {
    const server = fakeServer({ sessions: [{ id: "s1", title: "Parity chat", updated: new Date().toISOString() }] });
    const orig = server.f;
    const f = vi.fn(async (u: RequestInfo | URL, i?: RequestInit) => (String(u) === "/api/sessions/s1" ? new Response(JSON.stringify({ id: "s1", messages: [{ role: "user", content: "hi", sources: [] }] })) : orig(u, i)));
    mount({ ...server, f: f as unknown as typeof fetch });
    await userEvent.click(agent());
    await userEvent.click(await screen.findByRole("button", { name: /Parity chat/ }));
    await waitFor(() => expect(useChatDock.getState().open).toBe(true));
    expect(JSON.parse(sessionStorage.getItem("kbchat.chat")!)).toMatchObject({ id: "kb-chat:s1" });
    });
  });

  it("with no notes or chats a quiet placeholder card says so (spark-chat off; on, the New chat card stands there)", () =>
    withFlag("spark-chat", false, async () => {
      mount(fakeServer(), {}, { listThink: async () => ({ capture_note: "x", notes: [] }) });
      await userEvent.click(think());
      expect(await screen.findByText("No think notes yet")).toBeInTheDocument();
      await userEvent.click(agent());
      expect(await screen.findByText("No chats yet")).toBeInTheDocument();
    }));

  it("'...' beside each fan offers New and Open full screen", async () => {
    await withFlag("spark-chat", false, async () => {
    mount();
    await userEvent.click(think());
    await userEvent.click(screen.getByRole("button", { name: "Think options" }));
    await userEvent.click(screen.getByRole("button", { name: "Open full screen" }));
    expect(host.go).toHaveBeenCalledWith("/think");
    await userEvent.click(agent());
    await userEvent.click(screen.getByRole("button", { name: "Agent options" }));
    await userEvent.click(screen.getByRole("button", { name: "New" }));
    expect(useChatDock.getState().open).toBe(true);
    });
  });
});

/** The pointer leaves the spot of the last click (further than the still-click threshold). */
const moveAway = () => fireEvent.mouseMove(window, { clientX: 60, clientY: 60 });

describe("legends", () => {
  it("pressing a type name in the types card hides or shows that type", async () => {
    mount();
    await userEvent.click(screen.getByRole("button", { name: /show page types/i }));
    moveAway();
    const person = screen.getByRole("button", { name: /^Person/ });
    expect(person).toHaveAttribute("aria-pressed", "false"); // hidden by default: dimmed
    await userEvent.click(person);
    expect(useGraphUi.getState().shownTypes?.has("person")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /^Topic/ }));
    expect(useGraphUi.getState().shownTypes?.has("topic")).toBe(false);
  });

  it("the types card has concepts on the left of the divider and sources on the right", () =>
    withFlag("graph-intent", false, () => {
    mount();
    const card = screen.getByRole("group", { name: "Page types" });
    const [left, right] = [...card.children].filter((e) => e.tagName === "DIV") as HTMLElement[];
    expect(left!.querySelector("[data-type=topic]")).not.toBeNull();
    expect(right!.querySelector("[data-type=paper]")).not.toBeNull();
    expect(left!.querySelector("[data-type=paper]")).toBeNull();
    // the divider sits between the two groups
    expect(left!.nextElementSibling).toHaveAttribute("aria-hidden", "true");
    expect(left!.nextElementSibling!.nextElementSibling).toBe(right);
    }));

  // eight themes with 8, 7 ... 1 pages each, so the counts differ and the list is longer than five
  const themed = Array.from({ length: 8 }, (_, t) => Array.from({ length: 8 - t }, (_, i) => ({ ...sampleNodes[0]!, id: `t${t}-p${i}`, areas: [`theme-${t}`] }))).flat();
  const openLegend = async () => {
    assignAreaColors(themed);
    mount(fakeServer(), { nodes: themed, visible: new Set(themed.map((n) => n.id)) });
    await userEvent.click(screen.getByRole("button", { name: /show colour names/i }));
    return screen.getByRole("group", { name: /colour legend/i });
  };

  it("legend-counts on: pressing the dots lists every theme with its count and there is no +N more row", () =>
    withFlag("legend-counts", true, async () => {
      const legend = await openLegend();
      const listed = within(legend).getAllByRole("button", { pressed: true });
      expect(listed).toHaveLength(8);
      expect(listed[0]).toHaveTextContent(/8$/);
      expect(within(legend).queryByRole("button", { name: /more|fewer/i })).toBeNull();
    }));

  it("legend-counts off: every theme is listed and there is no +N more row", () =>
    withFlag("legend-counts", false, async () => {
      const legend = await openLegend();
      expect(within(legend).getAllByRole("button", { pressed: true })).toHaveLength(8);
      expect(within(legend).queryByRole("button", { name: /more/ })).toBeNull();
    }));

  it("hovering a colour name lights that colour's pages and lets go on leaving", async () => {
    const legend = await openLegend();
    const page = themed.find((n) => n.areas[0] === "theme-3")!;
    const label = colorKey(page, effectiveColorBy(useGraphUi.getState().colorBy));
    const row = legend.querySelector<HTMLElement>(`button[data-row="${label}"]`)!;
    // right after the opening click the pointer has not moved: the row under it is not chosen
    fireEvent.mouseMove(row);
    await new Promise((r) => setTimeout(r, 200));
    expect(useGraphUi.getState().spotIds).toBeNull();
    expect(row.className).not.toMatch(/hover:bg-accent/);
    moveAway();
    fireEvent.mouseMove(row);
    await waitFor(() => expect(useGraphUi.getState().spotIds).not.toBeNull());
    expect([...useGraphUi.getState().spotIds!].sort()).toEqual(themed.filter((n) => colorKey(n, effectiveColorBy(useGraphUi.getState().colorBy)) === label).map((n) => n.id).sort());
    expect(useGraphUi.getState().spotIds!.size).toBe(5);
    fireEvent.mouseLeave(row);
    await waitFor(() => expect(useGraphUi.getState().spotIds).toBeNull());
  });

  it("hiding the colour under the pointer lets its spotlight go at once; a hidden colour lights nothing", async () => {
    const legend = await openLegend();
    const label = colorKey(themed.find((n) => n.areas[0] === "theme-2")!, effectiveColorBy(useGraphUi.getState().colorBy));
    const row = legend.querySelector<HTMLElement>(`button[data-row="${label}"]`)!;
    moveAway();
    fireEvent.mouseMove(row);
    await waitFor(() => expect(useGraphUi.getState().spotIds?.size).toBe(6));
    fireEvent.click(row);
    expect(useGraphUi.getState().spotIds).toBeNull();
    fireEvent.mouseLeave(row);
    fireEvent.mouseMove(row);
    await new Promise((r) => setTimeout(r, 200));
    expect(useGraphUi.getState().spotIds).toBeNull();
  });

  it("folding the legend leaves a spotlight it did not set (the source-kind dial shares it)", async () => {
    await openLegend();
    useGraphUi.setState({ spotIds: new Set(["t0-p0"]) });
    await userEvent.click(screen.getByRole("button", { name: "Hide the colour legend" }));
    expect([...useGraphUi.getState().spotIds!]).toEqual(["t0-p0"]);
  });

  it("pressing the colour dots spreads them into names; pressing a name hides that colour", async () => {
    mount();
    const legend = screen.getByRole("group", { name: /colour legend/i });
    expect(legend).toHaveAttribute("data-open", "false");
    await userEvent.click(screen.getByRole("button", { name: /show colour names/i }));
    expect(legend).toHaveAttribute("data-open", "true");
    const row = within(legend).getAllByRole("button", { pressed: true })[0]!;
    const label = row.getAttribute("data-row")!;
    moveAway();
    await userEvent.click(row);
    expect(useGraphUi.getState().hiddenKeys.has(label)).toBe(true);
    expect(row).toHaveAttribute("aria-pressed", "false");
  });

  it("hiding a colour or changing the colouring keeps the drawn types, also when they still come from the view's story", async () => {
    mount();
    expect(useGraphUi.getState().shownTypes).toBeUndefined();
    const legend = screen.getByRole("group", { name: /colour legend/i });
    await userEvent.click(screen.getByRole("button", { name: /show colour names/i }));
    moveAway();
    await userEvent.click(within(legend).getAllByRole("button", { pressed: true })[0]!);
    expect([...useGraphUi.getState().shownTypes!].sort()).toEqual([...schema.defaultVisible].sort());
    useGraphUi.setState({ shownTypes: undefined });
    await userEvent.selectOptions(within(legend).getByRole("combobox", { name: "Color by" }), "maturity");
    expect([...useGraphUi.getState().shownTypes!].sort()).toEqual([...schema.defaultVisible].sort());
  });

  it("a kb with no page of a default type: hiding one of its types keeps the others drawn", async () => {
    // every page is a company or a role; the kit's defaults (topic, idea, question) match none of them
    const own = parseSchema({ types: [{ id: "topic", label: "Topic", layer: "concept" }, { id: "company", label: "Company", layer: "concept" }, { id: "role", label: "Role", layer: "concept" }], default_visible: ["topic"] });
    const pages = [{ ...sampleNodes[0]!, id: "c1", type: "company" }, { ...sampleNodes[0]!, id: "r1", type: "role" }];
    mount(fakeServer(), { nodes: pages, visible: new Set(["c1", "r1"]), schema: own, shownTypes: new Set(["topic", "company", "role"]) });
    await userEvent.click(screen.getByRole("button", { name: /show page types/i }));
    moveAway();
    await userEvent.click(screen.getByRole("button", { name: /^Company/ }));
    const shown = useGraphUi.getState().shownTypes;
    expect(shown?.has("company")).toBe(false);
    expect(shown?.has("role")).toBe(true);
  });

  it("graph-intent on: a Concepts / Sources switch; Concepts lists no source type and offers the concept colourings", () =>
    withFlag("knowledge-health", false, () => withFlag("graph-intent", true, async () => {
      mount();
      const sw = screen.getByRole("radiogroup", { name: /what the graph shows/i });
      expect(within(sw).getByRole("radio", { name: "Concepts" })).toHaveAttribute("aria-checked", "true");
      const card = screen.getByRole("group", { name: "Page types" });
      expect(card.querySelector("[data-type=topic]")).not.toBeNull();
      expect(card.querySelector("[data-type=paper]")).toBeNull();
      // one group alone is centred: no divider, no empty half beside it
      expect(card).toHaveAttribute("data-groups", "1");
      expect(card.querySelector("span[aria-hidden].w-px")).toBeNull();
      const pick = within(screen.getByRole("group", { name: /colour legend/i })).getByRole("combobox", { name: "Color by" });
      expect(within(pick).getAllByRole("option").map((o) => o.textContent)).toEqual(["theme", "type", "maturity", "recency", "source count"]);
      await userEvent.click(within(sw).getByRole("radio", { name: "Sources" }));
      const shown = useGraphUi.getState().shownTypes!;
      expect(shown.has("paper")).toBe(true);
      expect(shown.has("topic")).toBe(true);
      expect(useGraphUi.getState().colorBy).toBe("format");
    })));

  it("graph-intent on, Sources view: the source types are listed and the colourings are the source ones", () =>
    withFlag("knowledge-health", false, () => withFlag("graph-intent", true, () => {
      useGraphUi.setState({ colorBy: "format" });
      mount(fakeServer(), { visible: new Set(sampleNodes.map((n) => n.id)), shownTypes: new Set([...schema.defaultVisible, "paper"]) });
      expect(within(screen.getByRole("radiogroup", { name: /what the graph shows/i })).getByRole("radio", { name: "Sources" })).toHaveAttribute("aria-checked", "true");
      expect(screen.getByRole("group", { name: "Page types" }).querySelector("[data-type=paper]")).not.toBeNull();
      const pick = within(screen.getByRole("group", { name: /colour legend/i })).getByRole("combobox", { name: "Color by" });
      expect(within(pick).getAllByRole("option").map((o) => o.textContent)).toEqual(["format", "digest status", "date added"]);
      // the colour key lists the sources' values only: the concepts beside them are neutral
      const rows = [...screen.getByRole("group", { name: /colour legend/i }).querySelectorAll("button[data-row]")].map((b) => b.getAttribute("data-row"));
      expect(rows).toEqual(["paper"]);
    })));

  it("knowledge-health on: the switch stays Concepts / Sources; Health (typed) colours the concepts by source support", () =>
    withFlag("graph-intent", true, () =>
      withFlag("knowledge-health", true, async () => {
        mount();
        const sw = screen.getByRole("radiogroup", { name: /what the graph shows/i });
        expect(within(sw).getAllByRole("radio").map((r) => r.textContent)).toEqual(["Concepts", "Sources"]);
        // Health is a lens on concepts, reached from the line ("health"), so the switch keeps Concepts checked
        act(() => void applySubject("health", schema, new Set(schema.defaultVisible)));
        expect(useGraphUi.getState().colorBy).toBe("support");
        expect(within(sw).getByRole("radio", { name: "Concepts" })).toHaveAttribute("aria-checked", "true");
        const pick = within(screen.getByRole("group", { name: /colour legend/i })).getByRole("combobox", { name: "Color by" });
        expect(within(pick).getAllByRole("option").map((o) => o.textContent)).toEqual(["source support"]);
        // pressing the already-checked Concepts keeps Health instead of leaving it silently
        await userEvent.click(within(sw).getByRole("radio", { name: "Concepts" }));
        expect(useGraphUi.getState().colorBy).toBe("support");
        await userEvent.click(within(sw).getByRole("radio", { name: "Sources" }));
        expect(useGraphUi.getState().shownTypes?.has("paper")).toBe(true);
      })));

  it("knowledge-health off: the switch stays Concepts / Sources", () =>
    withFlag("graph-intent", true, () =>
      withFlag("knowledge-health", false, () => {
        mount();
        const sw = screen.getByRole("radiogroup", { name: /what the graph shows/i });
        expect(within(sw).getAllByRole("radio").map((r) => r.textContent)).toEqual(["Concepts", "Sources"]);
      })));

  it("graph-intent off: no switch, and the types card keeps its source side", () =>
    withFlag("graph-intent", false, () => {
      mount();
      expect(screen.queryByRole("radiogroup", { name: /what the graph shows/i })).toBeNull();
      expect(screen.getByRole("group", { name: "Page types" }).querySelector("[data-type=paper]")).not.toBeNull();
    }));

  it("two clicks on the same spot open and close the colour legend, and never hide the name under the pointer", async () => {
    mount();
    const legend = screen.getByRole("group", { name: /colour legend/i });
    await userEvent.click(screen.getByRole("button", { name: /show colour names/i }));
    expect(legend).toHaveAttribute("data-open", "true");
    // the pointer has not moved: the name that slid under it does not take the click
    await userEvent.click(within(legend).getAllByRole("button", { pressed: true })[0]!);
    expect(legend).toHaveAttribute("data-open", "false");
    expect(useGraphUi.getState().hiddenKeys.size).toBe(0);
  });

  it("a drift under the threshold still counts as the same spot", async () => {
    mount();
    const legend = screen.getByRole("group", { name: /colour legend/i });
    await userEvent.click(screen.getByRole("button", { name: /show colour names/i }));
    fireEvent.mouseMove(window, { clientX: 2, clientY: 2 });
    await userEvent.click(within(legend).getAllByRole("button", { pressed: true })[0]!);
    expect(legend).toHaveAttribute("data-open", "false");
    expect(useGraphUi.getState().hiddenKeys.size).toBe(0);
  });

  it("the types card follows the same rule: two clicks on the same spot open and close it", async () => {
    mount();
    const card = screen.getByRole("group", { name: "Page types" });
    const before = useGraphUi.getState().shownTypes;
    await userEvent.click(screen.getByRole("button", { name: /show page types/i }));
    expect(card).toHaveAttribute("data-open", "true");
    await userEvent.click(screen.getByRole("button", { name: /^Topic/ }));
    expect(card).toHaveAttribute("data-open", "false");
    expect(useGraphUi.getState().shownTypes).toBe(before);
  });

  it("a double click on a name in the open types card folds it and undoes the first click's change", async () => {
    mount();
    const card = screen.getByRole("group", { name: "Page types" });
    await userEvent.click(screen.getByRole("button", { name: /show page types/i }));
    moveAway();
    const shown = () => useGraphUi.getState().shownTypes?.has("topic") ?? true; // null: the defaults, topic among them
    const before = shown();
    const types = useGraphUi.getState().shownTypes;
    const topic = screen.getByRole("button", { name: /^Topic/ });
    fireEvent.click(topic, { clientX: 200, clientY: 200, detail: 1 });
    expect(shown()).toBe(!before); // the first click changes it
    fireEvent.click(screen.getByRole("button", { name: /^Topic/ }), { clientX: 201, clientY: 200, detail: 2 });
    expect(card).toHaveAttribute("data-open", "false");
    expect(shown()).toBe(before);
    expect(useGraphUi.getState().shownTypes).toBe(types); // the very same value, not a copy
  });

  it("a slow second click on the same name (no double-click timing) is a plain click", async () => {
    mount();
    const card = screen.getByRole("group", { name: "Page types" });
    await userEvent.click(screen.getByRole("button", { name: /show page types/i }));
    moveAway();
    const topic = () => screen.getByRole("button", { name: /^Topic/ });
    fireEvent.click(topic(), { clientX: 200, clientY: 200, detail: 1 });
    fireEvent.click(topic(), { clientX: 200, clientY: 200, detail: 1 });
    expect(card).toHaveAttribute("data-open", "true");
  });

  it("two clicks on a name with a move between them are two plain clicks, and the card stays open", async () => {
    mount();
    const card = screen.getByRole("group", { name: "Page types" });
    await userEvent.click(screen.getByRole("button", { name: /show page types/i }));
    moveAway();
    const shown = () => useGraphUi.getState().shownTypes?.has("topic") ?? true; // null: the defaults, topic among them
    const before = shown();
    const topic = screen.getByRole("button", { name: /^Topic/ });
    fireEvent.click(topic, { clientX: 200, clientY: 200, detail: 1 });
    fireEvent.mouseMove(window, { clientX: 260, clientY: 200 });
    expect(shown()).toBe(!before);
    // the props here stay as mounted, so the row still reads as shown: a plain second click hides it again, no undo
    fireEvent.click(screen.getByRole("button", { name: /^Topic/ }), { clientX: 260, clientY: 200, detail: 1 });
    expect(card).toHaveAttribute("data-open", "true");
    expect(shown()).toBe(!before);
  });

  it("the header reads Color by, with a dropdown of the concept colourings; sources add theirs once drawn", async () => {
    mount();
    const legend = screen.getByRole("group", { name: /colour legend/i });
    const pick = within(legend).getByRole("combobox", { name: "Color by" });
    expect(legend).toHaveTextContent("Color by");
    expect(within(legend).getByRole("button", { name: "Hide the colour legend" })).toBeInTheDocument();
    expect(within(pick).getAllByRole("option").map((o) => o.textContent)).toEqual(["theme", "type", "maturity", "recency", "source count"]);
    await userEvent.selectOptions(pick, "maturity");
    expect(useGraphUi.getState().colorBy).toBe("status");
  });

  it("with a source on screen the dropdown also offers digest status and date added", () =>
    withFlag("graph-intent", false, () => {
    const paper = sampleNodes.find((n) => n.layer === "source")!;
    mount(fakeServer(), { visible: new Set(sampleNodes.map((n) => n.id)) });
    expect(paper).toBeDefined();
    const pick = within(screen.getByRole("group", { name: /colour legend/i })).getByRole("combobox", { name: "Color by" });
    expect(within(pick).getAllByRole("option").map((o) => o.textContent)).toEqual(["theme", "type", "maturity", "recency", "source count", "digest status", "date added"]);
    }));

  it("a continuous colouring shows one gradient bar with its two ends, not swatches", async () => {
    useGraphUi.setState({ colorBy: "recency" });
    mount();
    const legend = screen.getByRole("group", { name: /colour legend/i });
    expect(legend.querySelector("[data-row=bar]")).not.toBeNull();
    expect(within(legend).queryAllByRole("button", { pressed: true })).toHaveLength(0);
    await userEvent.click(screen.getByRole("button", { name: /show colour names/i }));
    expect(legend).toHaveTextContent("this week");
  });

  it("the legend slides down out of the Think fan's arc, and back when Think closes", async () => {
    window.innerHeight = 900;
    const many = Array.from({ length: 9 }, (_, i) => ({ name: `n${i}.md`, mtime: 1_700_000_000 + i, size: 1 }));
    mount(fakeServer(), {}, { listThink: async () => ({ capture_note: "x", notes: many }) });
    const legend = screen.getByRole("group", { name: /colour legend/i });
    const top = () => parseFloat(legend.style.top);
    const rest = top();
    await userEvent.click(think());
    const group = screen.getByRole("group", { name: "Think notes" });
    await within(group).findByRole("button", { name: /All think notes/ });
    const cards = within(group).getAllByRole("button").length;
    expect(legend).toHaveAttribute("data-shifted", "true");
    expect(top()).toBeGreaterThanOrEqual(rest);
    // the legend starts below the last card of the fan
    expect(top()).toBeGreaterThanOrEqual(fanReach(cards) + 11);
    await userEvent.click(think());
    expect(legend).toHaveAttribute("data-shifted", "false");
    expect(top()).toBeCloseTo(rest, 3);
    window.innerHeight = 768;
  });

  it("opening Think folds a spread legend back so it never sits under the fan", async () => {
    mount();
    await userEvent.click(screen.getByRole("button", { name: /show colour names/i }));
    expect(useCorners.getState().order).toContain("legend");
    await userEvent.click(think());
    expect(useCorners.getState().order).not.toContain("legend");
  });

  it("keeps the old stats line for assistive tech", () => {
    mount();
    expect(screen.getByTestId("graph-stats")).toHaveTextContent("3 of 7 pages");
  });
});


describe("flag spark-chat on the agent fan", () => {
  const day = (d: number) => new Date(Date.now() - d * 86400000).toISOString();
  const rows = [
    { id: "s1", title: "Parity chat", updated: day(0), status: "running" },
    { id: "s2", title: "Spectral bias", updated: day(1), status: "idle" },
    { id: "s3", title: "Tensor rank", updated: day(9), status: "idle" },
  ];

  it("on: New chat comes first, each chat says its status or day, and New chat opens an empty chat in the left panel", () =>
    withFlag("spark-chat", true, async () => {
      mount(fakeServer({ sessions: rows }));
      await userEvent.click(agent());
      const group = screen.getByRole("group", { name: "Agent chats" });
      await waitFor(() => expect(within(group).getAllByRole("button")).toHaveLength(4));
      expect(within(group).getAllByRole("button")[0]).toHaveAccessibleName("New chat");
      expect(within(group).getByRole("button", { name: "Parity chat, running" })).toBeInTheDocument();
      expect(within(group).getByRole("button", { name: "Spectral bias, yesterday" })).toBeInTheDocument();
      // the running chat carries the green dot
      expect(group.querySelectorAll(".bg-ok")).toHaveLength(1);
      await userEvent.click(within(group).getByRole("button", { name: "New chat" }));
      // flag spark-chat sends it to the left panel (SparkPanel.test.tsx), never the right dock
      expect(useSparkPanel.getState().open).toBe(true);
      expect(useChatDock.getState().open).toBe(false);
    }));

  it("off: no New chat card, the pills keep the relative age", () =>
    withFlag("spark-chat", false, async () => {
      mount(fakeServer({ sessions: rows }));
      await userEvent.click(agent());
      const group = screen.getByRole("group", { name: "Agent chats" });
      await within(group).findByRole("button", { name: /Parity chat/ });
      expect(within(group).queryByRole("button", { name: "New chat" })).not.toBeInTheDocument();
      expect(within(group).getByRole("button", { name: "Spectral bias, yesterday" })).toBeInTheDocument();
      expect(within(group).queryByRole("button", { name: /running/ })).not.toBeInTheDocument();
      expect(group.querySelectorAll(".bg-ok")).toHaveLength(0);
    }));
});

describe("flag pin-fan: the pinned corner is a fan", () => {
  const card = (name: RegExp | string) => within(document.querySelector('[data-fan="pins"]') as HTMLElement).getByRole("button", { name });

  it("opens a fan from the top-left: Pin this view first, then the pinned views newest first; a view applies and folds the fan", () =>
    withFlag("pin-fan", true, async () => {
      mount(fakeServer({ views: [{ id: "alpha", name: "Alpha view" }, { id: "beta", name: "Beta view" }] }));
      await userEvent.click(pins());
      await screen.findByRole("button", { name: /^Beta view/ });
      const fan = document.querySelector('[data-fan="pins"]') as HTMLElement;
      expect(fan).toHaveAttribute("data-open", "true");
      expect(screen.queryByRole("group", { name: "Views panel" })).toBeNull();
      const names = within(fan).getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? "");
      expect(names[0]).toBe("Pin this view");
      expect(names[1]).toMatch(/^Beta view/);
      expect(names[2]).toMatch(/^Alpha view/);
      await userEvent.click(card(/^Alpha view/));
      expect(useCorners.getState().activeView).toBe("alpha");
      expect(useGraphUi.getState().shownTypes).toBeNull(); // the spec said "all types"
      expect(fan).toHaveAttribute("data-open", "false");
    }));

  it("Pin this view asks for a name inline and posts it; the new view joins the fan", () =>
    withFlag("pin-fan", true, async () => {
      const server = fakeServer();
      mount(server);
      await userEvent.click(pins());
      await userEvent.click(card("Pin this view"));
      const input = screen.getByRole("textbox", { name: /name for the pinned view/i });
      await userEvent.clear(input);
      await userEvent.type(input, "My dive{Enter}");
      await waitFor(() => expect(server.calls.some((c) => c.method === "POST")).toBe(true));
      expect(server.calls.find((c) => c.method === "POST")!.body).toMatchObject({ name: "My dive" });
      expect(await screen.findByRole("button", { name: /^My dive/ })).toBeInTheDocument();
    }));

  it("'...' renames the open view inline (PATCH)", () =>
    withFlag("pin-fan", true, async () => {
      const server = fakeServer({ views: [{ id: "alpha", name: "Alpha view" }] });
      mount(server);
      await userEvent.click(pins());
      await userEvent.click(await screen.findByRole("button", { name: /^Alpha view/ }));
      await userEvent.click(pins());
      await userEvent.click(screen.getByRole("button", { name: "Pinned view options" }));
      await userEvent.click(screen.getByRole("button", { name: /^Rename/ }));
      const input = screen.getByRole("textbox", { name: /new name for the pinned view/i });
      expect(input).toHaveValue("Alpha view");
      await userEvent.clear(input);
      await userEvent.type(input, "Renamed{Enter}");
      await waitFor(() => expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ name: "Renamed" }));
    }));

  it("more pins than fit: the last card is All views and opens the gallery (graph-intent on)", () =>
    withFlag("pin-fan", true, () =>
      withFlag("graph-intent", true, async () => {
        resetGallery();
        const many = Array.from({ length: 30 }, (_, i) => ({ id: `v${i}`, name: `View ${i}` }));
        mount(fakeServer({ views: many }));
        await userEvent.click(pins());
        const all = await screen.findByRole("button", { name: /^All views, 30/ });
        expect(within(document.querySelector('[data-fan="pins"]') as HTMLElement).getAllByRole("button").length).toBeLessThan(30);
        await userEvent.click(all);
        expect(useGallery.getState().open).toBe(true);
      }),
    ));
});

describe("flag pin-fan without the gallery", () => {
  it("graph-intent off and more pins than the fan holds: the corner keeps the scrolling list, so every view stays reachable", () =>
    withFlag("pin-fan", true, () =>
      withFlag("graph-intent", false, async () => {
        const many = Array.from({ length: 30 }, (_, i) => ({ id: `v${i}`, name: `View ${i}` }));
        mount(fakeServer({ views: many }));
        await userEvent.click(pins());
        expect(await screen.findByRole("button", { name: /^View 0/ })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /^View 29/ })).toBeInTheDocument();
        expect(document.querySelector('[data-fan="pins"]')).toBeNull();
      }),
    ));
});

describe("graph-corners: one raised disc per corner, and the theme switch in the fourth", () => {
  const themeBtn = () => screen.queryByRole("button", { name: /switch to (dark|light) theme/i });

  it("flag on: the pin, brain and spark are raised discs that look the same open and closed", () =>
    withFlag("graph-corners", true, async () => {
      mount(fakeServer(), {}, { kind: "http" });
      for (const b of [pins(), think(), agent()]) expect(b).toHaveAttribute("data-disc");
      expect(screen.getByTestId("graph-corners")).toHaveClass("kb-corners");
      const before = think().className;
      await userEvent.click(think());
      expect(think()).toHaveAttribute("aria-expanded", "true");
      expect(think().className).toBe(before); // no "on" look: what it opened shows the state
      expect(think().querySelector("[data-icon=think]")?.tagName.toLowerCase()).toBe("svg");
    }));

  it("flag on: no theme corner (the switch is the app bar's own) and the bar is never told to leave its switch out", () =>
    withFlag("graph-corners", true, () => {
      mount(fakeServer(), {}, { kind: "http" });
      expect(themeBtn()).toBeNull();
      expect(useTheme.getState().elsewhere).toBe(false);
    }));

  it("flag off: the corners keep their bare icons and there is no theme corner", () =>
    withFlag("graph-corners", false, () => {
      mount(fakeServer(), {}, { kind: "http" });
      expect(pins()).not.toHaveAttribute("data-disc");
      expect(themeBtn()).toBeNull();
      expect(screen.getByTestId("graph-corners")).not.toHaveClass("kb-corners");
    }));
});

/** The loop's cards on screen (solid, fading or tilted), front first. */
const onScreen = () =>
  [...document.querySelectorAll<HTMLElement>("[data-corners=pin-loop] [data-slot]")]
    .sort((a, b) => Number(a.dataset.pos) - Number(b.dataset.pos))
    .map((li) => li.querySelector<HTMLButtonElement>("[data-view]")!);

describe("graph-corners: the pinned views hang from the pin in a loop", () => {
  const many = Array.from({ length: 16 }, (_, i) => ({ id: `v${i}`, name: `View ${i}` }));
  // the pinned cards on screen, front first (the graph's own views open the loop as `view:…` cards)
  const cards = () => onScreen().filter((b) => !b.dataset.view!.startsWith("view:"));

  it("as many cards as fit between the pin and the spark; a short window shows fewer", () => {
    expect([loopSolid(852), loopSolid(700), loopSolid(560)]).toEqual([5, 4, 3]);
    // one arc bending left, each card turned a little more; the last solid card's bottom-left corner meets the border
    const p = arcPlaces(5);
    expect(p[1]!.deg).toBeGreaterThan(0);
    expect(p[4]!.deg).toBeGreaterThan(p[1]!.deg);
    expect(p[4]!.x).toBeLessThan(0);
    const bottomLeftX = p[4]!.x - 106 * Math.sin((p[4]!.deg * Math.PI) / 180);
    expect(Math.abs(bottomLeftX + 38)).toBeLessThan(1); // the loop hangs from the pin's centre (36px in); 2px past the border
  });

  it("past the window's count both ends always show, no place is taken twice, and nothing is dropped that fits", () => {
    for (const base of [3, 4, 5]) {
      expect(loopSlots(base, base).slots.every((x) => x === "solid")).toBe(true);
      for (let n = base + 1; n <= base + 8; n++) {
        const { solid, slots } = loopSlots(n, base);
        const named = slots.filter(Boolean) as string[];
        const ends = named.filter((x) => x !== "solid");
        expect(new Set(ends).size).toBe(ends.length); // each end place once
        expect(ends).toContain("b1");
        expect(ends).toContain("t1");
        expect(solid).toBeGreaterThanOrEqual(2);
        expect(named.length).toBe(Math.min(n, solid + 5)); // every card that has a place is shown
        if (ends.includes("b2")) expect(slots.indexOf("b2")).toBe(solid + 1);
        expect(slots.indexOf("t1")).toBe(n - 1);
        if (n - solid >= 4) expect(ends).toEqual(expect.arrayContaining(["b1", "b2", "t1", "t2"])); // two below, two above
      }
    }
  });

  it("pressing a card applies its view, and the view on screen has a blue dot and name", () =>
    withFlag("graph-intent", false, () => withFlag("graph-corners", true, async () => {
      const server = fakeServer({ views: [{ id: "a", name: "Alpha" }, { id: "b", name: "Beta" }] });
      mount(server, {}, { kind: "http" });
      await userEvent.click(pins());
      await waitFor(() => expect(cards()).toHaveLength(2));
      expect(cards()[0]).toHaveAccessibleName("Beta"); // newest first
      await userEvent.click(cards()[1]!);
      expect(useCorners.getState().activeView).toBe("a");
      await waitFor(() => expect(document.querySelector("[data-view=a]")).toHaveAttribute("aria-current", "true"));
    })));

  it("with more views than fit, the faded ends turn the loop and the pin never moves", () =>
    withFlag("graph-intent", false, () => withFlag("graph-corners", true, async () => {
      mount(fakeServer({ views: many }), {}, { kind: "http" });
      await userEvent.click(pins());
      await waitFor(() => expect(cards().length).toBeGreaterThan(1));
      const pinAt = pins().getBoundingClientRect().top;
      expect(cards().length).toBeLessThan(many.length);
      // after the solid cards, the next is half there and the one after almost gone; three turned past fade above the pin
      expect(cards().map((c) => c.dataset.end ?? "solid").filter((e) => e !== "solid").sort()).toEqual(["b1", "b2", "t1", "t2", "t3"]);
      const secondBefore = cards()[1]!.dataset.view;
      const frontBefore = cards()[0]!.dataset.view;
      await userEvent.click(cards().find((c) => c.dataset.end === "b1")!);
      expect(cards()[0]!.dataset.view).toBe(secondBefore); // turned forward by one
      await userEvent.click(cards().find((c) => c.dataset.end === "t1")!);
      expect(cards()[0]!.dataset.view).toBe(frontBefore); // and back again
      expect(useCorners.getState().activeView).toBeNull(); // a faded end turns, it does not apply
      expect(pins().getBoundingClientRect().top).toBe(pinAt);
    })));

  it("nothing pinned and no views to list (graph-intent off): the corner says how to pin", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", false, async () => {
        mount(fakeServer(), {}, { kind: "http" });
        await userEvent.click(pins());
        expect(await screen.findByText(/Type \/pin in the search line/)).toBeInTheDocument();
      }),
    ));

  it("flag off: the pinned corner keeps its list", () =>
    withFlag("graph-corners", false, async () => {
      mount(fakeServer({ views: [{ id: "a", name: "Alpha" }] }), {}, { kind: "http" });
      await userEvent.click(pins());
      await screen.findByText("Alpha");
      expect(document.querySelector("[data-corners=pin-loop]")).toBeNull();
    }));
});

describe("graph-corners: the graph's views open the pin's loop", () => {
  const options = () => [...document.querySelectorAll<HTMLButtonElement>("[data-corners=pin-loop] [data-view^='view:']")];

  it("on: the loop starts with the views, then the pinned ones, Concepts on; picking Sources (no Health) draws the sources alone", () =>
    withFlag("graph-corners", true, () =>
      withFlag("knowledge-health", false, () =>
      withFlag("graph-intent", true, async () => {
        mount(fakeServer({ views: [{ id: "a", name: "Alpha" }] }), {}, { kind: "http" });
        expect(document.querySelector("[data-corners=subject]")).toBeNull(); // no switch beside the line
        await userEvent.click(pins());
        await waitFor(() => expect(options().length).toBeGreaterThanOrEqual(2));
        expect(options().slice(0, 2).map((o) => o.dataset.view)).toEqual(["view:concepts", "view:sources"]);
        expect(options()[0]).toHaveAttribute("aria-current", "true");
        // the pinned view follows the graph's views in the same loop
        const all = [...document.querySelectorAll<HTMLElement>("[data-corners=pin-loop] [data-pos]")]
          .sort((a, b) => Number(a.dataset.pos) - Number(b.dataset.pos))
          .map((li) => li.querySelector<HTMLButtonElement>("[data-view]")!.dataset.view);
        expect(all.indexOf("a")).toBeGreaterThan(all.indexOf("view:sources"));
        await userEvent.click(options()[1]!);
        const drawn = [...useGraphUi.getState().shownTypes!];
        const layerOf = new Map(schema.types.map((t) => [t.id, t.layer] as const));
        expect(drawn.length).toBeGreaterThan(0);
        expect(drawn.every((t) => layerOf.get(t) === "source")).toBe(true);
      })),
    ));

  it("on, with Health: the Sources card is the way into Health (the concepts by source support)", () =>
    withFlag("graph-corners", true, () =>
      withFlag("knowledge-health", true, () =>
        withFlag("graph-intent", true, async () => {
          mount(fakeServer(), {}, { kind: "http" });
          await userEvent.click(pins());
          await waitFor(() => expect(document.querySelector("[data-view='view:sources']")).not.toBeNull());
          await userEvent.click(document.querySelector<HTMLButtonElement>("[data-view='view:sources']")!);
          const s = useGraphUi.getState();
          const layerOf = new Map(schema.types.map((t) => [t.id, t.layer] as const));
          expect([...s.shownTypes!].every((t) => layerOf.get(t) === "concept")).toBe(true);
          expect(s.colorBy).toBe("support");
        }),
      ),
    ));

  it("on: with the sources drawn, Sources is the view marked in the pin", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", true, async () => {
        const sourceTypes = schema.types.filter((t) => t.layer === "source").map((t) => t.id);
        mount(fakeServer(), { shownTypes: new Set(sourceTypes) }, { kind: "http" });
        await userEvent.click(pins());
        await waitFor(() => expect(document.querySelector("[data-view='view:sources']")).toHaveAttribute("aria-current", "true"));
        expect(document.querySelector("[data-view='view:concepts']")).not.toHaveAttribute("aria-current");
      }),
    ));

  it("on: a few cards past the window's count keep both ends: two fading below and one turned past above the pin", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", true, async () => {
        mount(fakeServer({ views: ["a", "b", "c", "d"].map((id) => ({ id, name: id })) }), {}, { kind: "http" });
        await userEvent.click(pins());
        await waitFor(() => expect(onScreen().length).toBeGreaterThan(3));
        const ends = onScreen().map((b) => b.dataset.end).filter(Boolean);
        expect(ends).toEqual(expect.arrayContaining(["b1", "b2", "t1", "t2"]));
        // the top card hangs from the pin's centre: its corner is a quarter under the disc
        const top = document.querySelector<HTMLElement>("[data-corners=pin-loop]")!;
        expect(top.style.left).toBe("36px");
        expect(top.style.top).toBe("36px");
      }),
    ));

  it("on: with more cards than fit, a faded end turns the loop of views and pinned ones without picking", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", true, async () => {
        const many = Array.from({ length: 12 }, (_, i) => ({ id: `v${i}`, name: `View ${i}` }));
        mount(fakeServer({ views: many }), {}, { kind: "http" });
        await userEvent.click(pins());
        await waitFor(() => expect(onScreen().length).toBeGreaterThan(1));
        expect(onScreen()[0]!.dataset.view).toBe("view:concepts");
        const typesBefore = useGraphUi.getState().shownTypes;
        const second = onScreen()[1]!.dataset.view;
        await userEvent.click(onScreen().find((b) => b.dataset.end === "b1")!);
        expect(onScreen()[0]!.dataset.view).toBe(second);
        expect(useGraphUi.getState().shownTypes).toBe(typesBefore); // turning picks nothing
        expect(useCorners.getState().activeView).toBeNull();
      }),
    ));

  it("on: the loop reads the graph's views, the pinned ones, then the placeholders V1 to V3, which pick nothing", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", true, () => withFlag("graph.artifacts", false, async () => {
        mount(fakeServer({ views: [{ id: "a", name: "Alpha" }] }), {}, { kind: "http" });
        await userEvent.click(pins());
        const order = () =>
          [...document.querySelectorAll<HTMLElement>("[data-corners=pin-loop] [data-pos]")]
            .map((li) => li.querySelector<HTMLButtonElement>("[data-view]")!)
            .map((b) => b.getAttribute("aria-label")!.replace(/, turn the pile.*$/, ""));
        await waitFor(() => expect(order()).toContain("Alpha"));
        const names = order();
        expect(names.slice(0, 2)).toEqual(["Concepts", "Sources"]);
        expect(names.slice(-3)).toEqual(["V1", "V2", "V3"]);
        expect(names.indexOf("Alpha")).toBeLessThan(names.indexOf("V1"));
        const before = useGraphUi.getState().shownTypes;
        // a faded card turns the loop: turn until V1 is a solid card, then press it
        const v1 = () => document.querySelector<HTMLButtonElement>("[data-view='view:placeholder-v1']")!;
        for (let i = 0; i < 10 && v1().closest<HTMLElement>("[data-slot]")?.dataset.slot !== "solid"; i++)
          await userEvent.click(onScreen().find((b) => b.dataset.end === "b1")!);
        await userEvent.click(v1());
        expect(useGraphUi.getState().shownTypes).toBe(before);
        expect(await screen.findByText(/V1 is a placeholder/)).toBeInTheDocument();
        // no embedding in this kb: no Semantics card
        expect(document.querySelector("[data-view='view:map']")).toBeNull();
      })),
    ));

  it("on: the Citations card is in the loop only when the graph has cites relations", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", true, () =>
        withFlag("graph-relations", true, () => withFlag("graph.artifacts", true, async () => {
          const citations = () => document.querySelector("[data-view='view:citations']");
          const { unmount } = mount(fakeServer(), { relationKinds: new Set(["mentions"]) }, { kind: "http" });
          await userEvent.click(pins());
          await waitFor(() => expect(document.querySelector("[data-view='view:concepts']")).not.toBeNull());
          expect(citations()).toBeNull();
          unmount();
          mount(fakeServer(), { relationKinds: new Set(["mentions", "cites"]) }, { kind: "http" });
          await userEvent.click(pins());
          await waitFor(() => expect(citations()).not.toBeNull());
        })),
      ),
    ));

  it("graph.artifacts off: the Citations card is offered as before, cites relations or not", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", true, () =>
        withFlag("graph-relations", true, () => withFlag("graph.artifacts", false, async () => {
          mount(fakeServer(), { relationKinds: new Set(["mentions"]) }, { kind: "http" });
          await userEvent.click(pins());
          await waitFor(() => expect(document.querySelector("[data-view='view:citations']")).not.toBeNull());
          expect(document.querySelector("[data-view='view:intermediate']")).toBeNull();
          expect(document.querySelectorAll("[data-unfold]")).toHaveLength(0);
        })),
      ),
    ));

  it("on: a pinned view on screen is the only one marked, not the built-in view it looks like", () =>
    withFlag("graph-corners", true, () =>
      withFlag("graph-intent", true, async () => {
        mount(fakeServer({ views: [{ id: "a", name: "Alpha" }] }), {}, { kind: "http" });
        await userEvent.click(pins());
        await waitFor(() => expect(document.querySelector("[data-view=a]")).not.toBeNull());
        act(() => useCorners.getState().setActive("a"));
        await waitFor(() => expect(document.querySelector("[data-view=a]")).toHaveAttribute("aria-current", "true"));
        expect(document.querySelectorAll("[data-corners=pin-loop] [aria-current=true]")).toHaveLength(1);
      }),
    ));

  it("page types: on, a small dark dot inside the card folds it; off, the round minus beside it", async () => {
    for (const on of [true, false]) {
      await withFlag("graph-corners", on, async () => {
        useCorners.setState({ order: ["types"] });
        const { unmount } = mount(fakeServer(), {}, { kind: "http" });
        const fold = await screen.findByRole("button", { name: "Hide the page types" });
        if (on) expect(fold).toHaveAttribute("data-fold", "dot");
        else expect(fold).not.toHaveAttribute("data-fold");
        await userEvent.click(fold);
        expect(useCorners.getState().order).not.toContain("types");
        unmount();
      });
    }
  });

  it("graph-corners off: no views in the pin, and the Concepts / Sources switch stays beside the line", () =>
    withFlag("graph-corners", false, () =>
      withFlag("graph-intent", true, async () => {
        mount(fakeServer({ views: [{ id: "a", name: "Alpha" }] }), {}, { kind: "http" });
        expect(document.querySelector("[data-corners=subject]")).not.toBeNull();
        await userEvent.click(pins());
        await screen.findByText("Alpha");
        expect(document.querySelector("[data-view^='view:']")).toBeNull();
      }),
    ));
});

describe("graph.artifacts: one card per layer, the layer's other views tucked under it", () => {
  const go = vi.fn();
  const views = [
    { id: "dependencies", name: "Dependencies", types: ["Repo"] },
    { id: "structure", name: "Code structure", types: ["Repo"] },
    { id: "options", name: "Options", types: ["Repo"] },
  ];
  const CODE = "view:intermediate";
  beforeEach(() => go.mockClear());
  afterEach(() => act(() => useArtifactLayer.getState().register([], false, null, () => {})));
  const names = () => onScreen().map((b) => b.getAttribute("aria-label"));
  const piled = (key: string) => [...document.querySelectorAll<HTMLButtonElement>(`[data-pile='${key}'] [data-view]`)].map((b) => b.dataset.view);
  const unfold = () => document.querySelector<HTMLButtonElement>(`[data-unfold='${CODE}']`)!;
  const on = (fn: () => Promise<void>) => withFlag("graph-corners", true, () => withFlag("graph-intent", true, () => withFlag("graph.artifacts", true, fn)));

  const rad = (d: number) => (d * Math.PI) / 180;
  const W = SUB_W;
  // the box of a card turned about its top-left corner: its right, top and bottom edges
  const right = (p: { x: number; deg: number }) => p.x + W * Math.cos(rad(p.deg));
  const top = (p: { y: number; deg: number }) => p.y - Math.max(0, W * Math.sin(rad(-p.deg)));
  const bottom = (p: { y: number; deg: number }) => p.y + SUB_H * Math.cos(rad(p.deg)) + Math.max(0, W * Math.sin(rad(p.deg)));

  it("the unfolded cards are smaller than their card, run right of it in a row that sags a little, each partly over the one before, and close up before they leave their room", () => {
    expect(rowPlaces(0)).toEqual([]);
    // smaller than a card of the loop, the same shape
    expect(SUB_W).toBeLessThan(LOOP_W * 0.85);
    expect(SUB_W / SUB_H).toBeCloseTo(LOOP_W / LOOP_H, 1);
    const row = rowPlaces(4);
    expect(row[0]!.x).toBeGreaterThan(LOOP_W);
    expect(row.every((p, k) => k === 0 || p.x > row[k - 1]!.x)).toBe(true);
    // with all the room there is, a card still lies over the right edge of the one before, never over its name's side
    for (let k = 1; k < 4; k++) {
      const over = right(row[k - 1]!) - row[k]!.x;
      expect(over).toBeGreaterThan(ROW_OVERLAP - 4);
      expect(over).toBeLessThan(SUB_W / 4);
    }
    // first card down, last card up by as much
    expect(row[0]!.deg).toBeGreaterThan(0);
    expect(row[0]!.deg).toBeCloseTo(-row[3]!.deg);
    // eight cards in 1150px: one row still, the steps closed up, the last card inside
    const tight = rowPlaces(8, 1150);
    expect(rowCount(8, 1150)).toBe(1);
    expect(right(tight[7]!)).toBeLessThanOrEqual(1150);
    expect(tight[1]!.x - tight[0]!.x).toBeLessThan(row[1]!.x - row[0]!.x);
  });

  it("a narrow graph area: the cards go on to a second row before any name is covered, every row inside its room", () => {
    for (const room of [900, 760, 600]) {
      const rows = rowCount(8, room);
      expect(rows).toBeGreaterThan(1);
      const places = rowPlaces(8, room);
      expect(places).toHaveLength(8);
      expect(Math.max(...places.map(right))).toBeLessThanOrEqual(room);
      // the rows are even (4 + 4, or 3 + 3 + 2), each starts at the same left edge, and none touches the one above
      const per = Math.ceil(8 / rows);
      for (let r = 1; r < rows; r++) {
        expect(places[r * per]!.x).toBe(places[0]!.x);
        expect(Math.min(...places.slice(r * per, (r + 1) * per).map(top))).toBeGreaterThan(Math.max(...places.slice((r - 1) * per, r * per).map(bottom)));
      }
      // in a row no card covers more than a third of the one before
      if (rows < 3) expect(places[1]!.x - places[0]!.x).toBeGreaterThanOrEqual(SUB_W * 0.66);
    }
  });

  it("the cards lie under the search line and above their reach, where the graph is framed from", () => {
    expect(rowReach(0)).toBe(0);
    for (const room of [Infinity, 900, 620])
      for (let n = 1; n <= 10; n++) {
        const places = rowPlaces(n, room);
        expect(LOOP_TOP + Math.min(...places.map(top))).toBeGreaterThan(SHELL_TOP_FOLDED + SEARCH_LINE_H + 6);
        expect(LOOP_TOP + Math.max(...places.map(bottom))).toBeLessThanOrEqual(rowReach(rowCount(n, room)));
      }
    // a row count kept while the room shrinks (a wider legend): the cards close up and stay in one row, inside the room
    const kept = rowPlaces(8, 1000, 1);
    expect(new Set(kept.map((p) => Math.round(p.y / 60))).size).toBe(1);
    expect(Math.max(...kept.map(right))).toBeLessThanOrEqual(1000);
  });

  it("on: Concepts, Sources and the intermediate layers, then the pinned views; no placeholders; the layer's other views unfold with the card's button", () =>
    on(async () => {
      act(() => useArtifactLayer.getState().register(views, true, null, go));
      mount(fakeServer({ views: [{ id: "a", name: "Alpha" }] }), {}, { kind: "http" });
      await userEvent.click(pins());
      await waitFor(() => expect(names()).toContain("Alpha"));
      expect(names()).toEqual(["Concepts", "Sources", "Intermediate layers", "Alpha"]);
      expect(document.querySelector("[data-view^='view:placeholder']")).toBeNull();
      // every view of the layer lies under its card, the first one too: the card itself is no view
      expect(piled(CODE)).toEqual(["view:artifact:dependencies", "view:artifact:structure", "view:artifact:options", "view:artifact:evidence"]);
      // each tucked card has its own picture
      const art = [...document.querySelectorAll(`[data-pile='${CODE}'] [data-view] svg`)].map((s) => s.innerHTML);
      expect(new Set(art).size).toBe(art.length);
      // nothing lies under Concepts or Sources here (no embedding, no cites): they have no button
      expect(document.querySelectorAll("[data-unfold]")).toHaveLength(1);
      // folded: the tucked cards cannot be pressed
      expect(unfold()).toHaveAttribute("aria-expanded", "false");
      expect(document.querySelector(`[data-pile='${CODE}']`)).toHaveAttribute("inert");
      // a pile unfolds only from the top place: its card rises there, the others follow round the loop
      const pos = (key: string) => document.querySelector(`[data-view='${key}']`)!.closest<HTMLElement>("[data-pos]")!.dataset.pos;
      expect(pos(CODE)).toBe("2");
      await userEvent.click(unfold());
      expect(unfold()).toHaveAttribute("aria-expanded", "true");
      expect(document.querySelector(`[data-pile='${CODE}']`)).not.toHaveAttribute("inert");
      expect(pos(CODE)).toBe("0");
      expect(names()).toEqual(["Intermediate layers", "Alpha", "Concepts", "Sources"]);
      // the graph is told how far down the cards reach, and frames itself below them
      expect(useCorners.getState().pileReach).toBe(rowReach(1));
      // an unfolded card is smaller than its card
      const optionsCard = document.querySelector<HTMLButtonElement>("[data-view='view:artifact:options']")!;
      expect(parseFloat(optionsCard.style.width)).toBe(SUB_W);
      expect(parseFloat(document.querySelector<HTMLButtonElement>(`[data-view='${CODE}']`)!.style.width)).toBe(LOOP_W);
      await userEvent.click(optionsCard);
      expect(go).toHaveBeenLastCalledWith("options", null);
      // the row stays out after a pick; the card itself opens the layer's first view
      expect(useCorners.getState().pile).toBe(CODE);
      await userEvent.click(document.querySelector<HTMLButtonElement>(`[data-view='${CODE}']`)!);
      expect(go).toHaveBeenLastCalledWith("dependencies", null);
      // Esc folds the row first, then closes the loop
      await userEvent.keyboard("{Escape}");
      expect(useCorners.getState().pile).toBeNull();
      expect(useCorners.getState().order).toContain("pins");
      // folded, the card is back in its own place
      expect(names()).toEqual(["Concepts", "Sources", "Intermediate layers", "Alpha"]);
      expect(useCorners.getState().pileReach).toBe(0);
      await userEvent.keyboard("{Escape}");
      expect(useCorners.getState().order).not.toContain("pins");
    }));

  it("on: the wheel turns a loop whose cards all fit, one card a notch, and folds a row that is out", () =>
    on(async () => {
      act(() => useArtifactLayer.getState().register(views, false, null, go));
      mount(fakeServer(), {}, { kind: "http" });
      await userEvent.click(pins());
      await waitFor(() => expect(names()).toEqual(["Concepts", "Sources", "Intermediate layers"]));
      const loop = document.querySelector<HTMLElement>("[data-corners=pin-loop]")!;
      const now = vi.spyOn(performance, "now");
      const wheel = (deltaY: number, at: number) => {
        now.mockReturnValue(at);
        fireEvent.wheel(loop, { deltaY });
      };
      const before = useGraphUi.getState().shownTypes;
      wheel(100, 1000);
      expect(names()).toEqual(["Sources", "Intermediate layers", "Concepts"]);
      // the rest of the same notch (or of a trackpad swipe) moves nothing more
      wheel(100, 1100);
      expect(names()).toEqual(["Sources", "Intermediate layers", "Concepts"]);
      wheel(-100, 2000);
      expect(names()).toEqual(["Concepts", "Sources", "Intermediate layers"]);
      expect(useGraphUi.getState().shownTypes).toBe(before); // turning picks nothing
      expect(go).not.toHaveBeenCalled();
      // a row that is out folds, and the loop carries on from the card that was lifted
      await userEvent.click(unfold());
      expect(names()[0]).toBe("Intermediate layers");
      wheel(100, 3000);
      expect(useCorners.getState().pile).toBeNull();
      expect(names()).toEqual(["Concepts", "Sources", "Intermediate layers"]);
      now.mockRestore();
    }));

  it("without the piles the wheel leaves a loop whose cards all fit as it is", () => {
    const two = ["a", "b"].map((id) => ({ id, name: id.toUpperCase(), created: new Date().toISOString(), spec: {} }));
    const loop = () => document.querySelector<HTMLElement>("[data-corners=pin-loop]")!;
    const { rerender } = render(<PinLoop open views={two} active={null} areaHeight={800} onApply={vi.fn()} empty="" />);
    expect(onScreen().map((b) => b.dataset.view)).toEqual(["b", "a"]);
    fireEvent.wheel(loop(), { deltaY: 100 });
    expect(onScreen().map((b) => b.dataset.view)).toEqual(["b", "a"]);
    rerender(<PinLoop open views={two} active={null} areaHeight={800} onApply={vi.fn()} empty="" wheelTurns />);
    fireEvent.wheel(loop(), { deltaY: 100 });
    expect(onScreen().map((b) => b.dataset.view)).toEqual(["a", "b"]);
  });

  it("on: a folded card names the view of its pile that is on screen, and only that view is marked", () =>
    on(async () => {
      act(() => useArtifactLayer.getState().register(views, false, "structure", go));
      mount(fakeServer(), {}, { kind: "http" });
      await userEvent.click(pins());
      await waitFor(() => expect(document.querySelector(`[data-view='${CODE}']`)).not.toBeNull());
      const code = document.querySelector<HTMLElement>(`[data-view='${CODE}']`)!;
      expect(code).not.toHaveAttribute("aria-current");
      expect(code).toHaveTextContent("Code structure");
      expect(document.querySelector("[data-view='view:artifact:structure']")).toHaveAttribute("aria-current", "true");
      expect(document.querySelectorAll("[data-corners=pin-loop] [aria-current=true]")).toHaveLength(1);
    }));

  it("on: Citations lies under Intermediate layers (a knowledge base with no artifact layer gets the card for it), not under Sources", () =>
    on(() =>
      withFlag("graph-relations", true, async () => {
        mount(fakeServer(), { relationKinds: new Set(["cites"]), relationCounts: new Map([["cites", 94]]) }, { kind: "http" });
        await userEvent.click(pins());
        await waitFor(() => expect(piled(CODE)).toEqual(["view:citations"]));
        expect(names()).toEqual(["Concepts", "Sources", "Intermediate layers"]);
        expect(document.querySelector("[data-pile='view:sources']")).toBeNull();
        // the card opens the first view under it
        await userEvent.click(document.querySelector<HTMLButtonElement>(`[data-view='${CODE}']`)!);
        expect(useGraphUi.getState().edgeStory).toBe("citations");
      }),
    ));

  it("on: with an artifact layer Citations comes after its views, and opens from an artifact view in one press", () =>
    on(() =>
      withFlag("graph-relations", true, async () => {
        act(() => useArtifactLayer.getState().register(views, true, "structure", go));
        mount(fakeServer(), { relationKinds: new Set(["cites"]) }, { kind: "http" });
        await userEvent.click(pins());
        await waitFor(() => expect(piled(CODE).at(-1)).toBe("view:citations"));
        expect(piled(CODE)).toHaveLength(5);
        await userEvent.click(unfold());
        await userEvent.click(document.querySelector<HTMLButtonElement>("[data-view='view:citations']")!);
        expect(go).toHaveBeenLastCalledWith(null);
        expect(useGraphUi.getState().edgeStory).toBe("citations");
      }),
    ));

  it("on: the ? on an unfolded card says what its view is based on, counted from the data; Esc closes it, then the row, then the loop", () =>
    on(async () => {
      const info = { types: { Repo: 10, Folder: 131 }, relations: { imports: 833 }, relationWords: { imports: "file A includes file B" }, generator: "code-toolkit v1", project: "demo", template: "codebase", repos: 10, pages: 7, facts: 21 };
      act(() => useArtifactLayer.getState().register([{ id: "dependencies", name: "Dependencies", hint: "Who imports whom", types: ["Repo", "Folder"], relations: ["imports"], color_by: "repo" }], true, null, go, info));
      mount(fakeServer(), {}, { kind: "http" });
      await userEvent.click(pins());
      await waitFor(() => expect(document.querySelector(`[data-unfold='${CODE}']`)).not.toBeNull());
      const ask = (key: string) => document.querySelector<HTMLButtonElement>(`[data-about='${key}']`)!;
      const panel = () => document.querySelector<HTMLElement>("[data-about-panel]");
      expect(ask("view:artifact:dependencies")).toHaveAccessibleName("What is Dependencies based on?");
      expect(panel()).toBeNull();
      await userEvent.click(unfold());
      await userEvent.click(ask("view:artifact:dependencies"));
      expect(ask("view:artifact:dependencies")).toHaveAttribute("aria-expanded", "true");
      expect(panel()).toHaveTextContent("Who imports whom");
      expect(panel()).toHaveTextContent("10 Repo · 131 Folder");
      expect(panel()).toHaveTextContent("imports (833): file A includes file B");
      expect(panel()).toHaveTextContent("code-toolkit v1");
      expect(panel()).toHaveTextContent("10 repositories of project demo");
      expect(go).not.toHaveBeenCalled(); // asking opens nothing
      // another card's ? takes its place
      await userEvent.click(ask("view:artifact:evidence"));
      expect(panel()).toHaveTextContent("7 pages whose text cites a fact");
      expect(panel()).toHaveTextContent("21 fact ids cited");
      expect(document.querySelectorAll("[data-about-panel]")).toHaveLength(1);
      // the same ? closes it
      await userEvent.click(ask("view:artifact:evidence"));
      expect(panel()).toBeNull();
      await userEvent.click(ask("view:artifact:evidence"));
      await userEvent.keyboard("{Escape}");
      expect(panel()).toBeNull();
      expect(useCorners.getState().pile).toBe(CODE);
      await userEvent.keyboard("{Escape}");
      expect(useCorners.getState().pile).toBeNull();
      expect(useCorners.getState().order).toContain("pins");
      // folding the row closes an open explanation with it
      await userEvent.click(unfold());
      await userEvent.click(ask("view:artifact:dependencies"));
      await userEvent.click(unfold());
      expect(useCorners.getState().about).toBeNull();
    }));
});

describe("graph-corners: the spark and the brain open quick lists", () => {
  const chats = [
    { id: "c1", title: "Oldest chat", updated: "2026-11-01T10:00:00Z", status: "idle" },
    { id: "c2", title: "Tensor rank vs CP rank", updated: "2026-11-02T10:00:00Z", status: "idle" },
    { id: "c3", title: "Why does AdamW decouple decay?", updated: "2026-11-03T10:00:00Z", status: "running" },
    { id: "c4", title: "What cites Gunasekar 2017?", updated: "2026-11-04T10:00:00Z", status: "idle" },
    { id: "c5", title: "Summarise the implicit bias paper", updated: "2026-11-05T10:00:00Z", status: "idle" },
  ];
  // the server lists them newest first
  const withChats = () => fakeServer({ sessions: [...chats].reverse() });

  it("the spark: the line takes the cursor, the four newest chats sit above it, the running one has a green spark", () =>
    withFlag("graph-corners", true, async () => {
      mount(withChats(), {}, { kind: "http" });
      await userEvent.click(agent());
      const line = await screen.findByRole("combobox", { name: "Ask something new, or find a chat" });
      expect(line).toHaveFocus();
      const list = screen.getByRole("listbox", { name: "Chats" });
      await waitFor(() => expect(within(list).getAllByRole("option")).toHaveLength(4));
      expect(within(list).queryByText("Oldest chat")).toBeNull(); // only the four newest
      const running = list.querySelector("[data-quick-row=c3] span")!;
      expect(running).toHaveClass("text-ok");
    }));

  it("the spark: typing filters every chat, and Enter starts a new chat with the line", () =>
    withFlag("graph-corners", true, async () => {
      const ask = vi.spyOn(useChatDock.getState(), "ask");
      mount(withChats(), {}, { kind: "http" });
      await userEvent.click(agent());
      const line = await screen.findByRole("combobox", { name: "Ask something new, or find a chat" });
      await userEvent.type(line, "oldest");
      const list = screen.getByRole("listbox", { name: "Chats" });
      await waitFor(() => expect(within(list).getAllByRole("option").map((o) => o.textContent)).toEqual([expect.stringContaining("Oldest chat")]));
      await userEvent.clear(line);
      await userEvent.type(line, "what is a junta?{Enter}");
      expect(ask).toHaveBeenCalledWith("what is a junta?");
      ask.mockRestore();
    }));

  it("the brain: the line writes a thought, the newest notes sit under it, a pick opens the note", () =>
    withFlag("graph-corners", true, async () => {
      const captureThink = vi.fn(async () => ({ name: "inbox.md", mtime: 1 }));
      mount(fakeServer(), {}, { kind: "http", captureThink } as never);
      await userEvent.click(think());
      const line = await screen.findByRole("combobox", { name: "Write a thought, or find a note" });
      expect(line).toHaveFocus();
      const list = screen.getByRole("listbox", { name: "Think notes" });
      await waitFor(() => expect(within(list).getAllByRole("option").map((o) => o.textContent)).toEqual([expect.stringContaining("c-note"), expect.stringContaining("b-note"), expect.stringContaining("a-note")]));
      await userEvent.click(within(list).getAllByRole("option")[1]!);
      expect(host.go).toHaveBeenCalledWith("/think", { note: "b-note.md" });
      await userEvent.click(think());
      await userEvent.type(await screen.findByRole("combobox", { name: "Write a thought, or find a note" }), "rank is not additive{Enter}");
      await waitFor(() => expect(captureThink).toHaveBeenCalledWith("rank is not additive"));
    }));

  it("the spark: the up arrow picks an older chat and Enter opens it; Enter on an empty line does nothing", () =>
    withFlag("graph-corners", true, async () => {
      const ask = vi.spyOn(useChatDock.getState(), "ask");
      mount(withChats(), {}, { kind: "http" });
      await userEvent.click(agent());
      const line = await screen.findByRole("combobox", { name: "Ask something new, or find a chat" });
      await waitFor(() => expect(within(screen.getByRole("listbox", { name: "Chats" })).getAllByRole("option")).toHaveLength(4));
      await userEvent.keyboard("{Enter}");
      expect(ask).not.toHaveBeenCalled();
      expect(line).toHaveFocus();
      await userEvent.keyboard("{ArrowUp}{ArrowUp}");
      const picked = within(screen.getByRole("listbox", { name: "Chats" })).getByRole("option", { selected: true });
      expect(line).toHaveAttribute("aria-activedescendant", picked.id);
      expect(picked).toHaveTextContent("What cites Gunasekar 2017?"); // the second newest, one step further from the line
      await userEvent.keyboard("{Enter}");
      expect(screen.queryByRole("combobox", { name: "Ask something new, or find a chat" })).toBeNull();
      expect(ask).not.toHaveBeenCalled();
      ask.mockRestore();
    }));

  it("Esc closes the list once and gives the focus back to its button", () =>
    withFlag("graph-corners", true, async () => {
      mount(fakeServer(), {}, { kind: "http" });
      await userEvent.click(think());
      await screen.findByRole("combobox", { name: "Write a thought, or find a note" });
      await userEvent.keyboard("{Escape}");
      expect(screen.queryByRole("combobox", { name: "Write a thought, or find a note" })).toBeNull();
      expect(think()).toHaveFocus();
    }));

  it("flag off: the spark and the brain still open their fans", () =>
    withFlag("graph-corners", false, async () => {
      mount(fakeServer(), {}, { kind: "http" });
      await userEvent.click(think());
      expect(screen.queryByRole("combobox", { name: "Write a thought, or find a note" })).toBeNull();
      expect(await screen.findByText("b-note")).toBeInTheDocument(); // a fan card
    }));
});
