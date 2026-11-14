import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes, sampleSnapshot } from "../../fixtures";
import { parseSchema } from "../../schema";
import { applySubject } from "../../subject";
import { assignAreaColors } from "../../style";
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
