import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { sampleNodes, sampleSnapshot } from "../../fixtures";
import { parseSchema } from "../../schema";
import { DEFAULT_PREFS, useGraphUi } from "../../store";
import { useChatDock } from "../../tools/chatDockStore";
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
  useGraphUi.setState({ ...DEFAULT_PREFS, shownTypes: undefined, predicate: null, shownDepths: null, hiddenKeys: new Set(), spotlight: null, view: null });
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
  it("lists the pinned views, newest data from GET /api/views, and applies one through the spec", async () => {
    const applyView = vi.fn();
    mount(fakeServer({ views: [{ id: "alpha", name: "Alpha view" }, { id: "beta", name: "Beta view" }] }), { applyView });
    await userEvent.click(pins());
    const alpha = await screen.findByRole("button", { name: /^Alpha view/ });
    expect(screen.getByRole("button", { name: /^Beta view/ })).toBeInTheDocument();
    await userEvent.click(alpha);
    expect(alpha).toHaveAttribute("aria-pressed", "true");
    expect(useGraphUi.getState().shownTypes).toBeNull(); // the spec said "all types"
  });

  it("pins the current view with a name typed inline (POST /api/views {name, spec})", async () => {
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

  it("zero pins: only the plus card, the divider and Recent", async () => {
    mount(fakeServer());
    await userEvent.click(pins());
    await screen.findByRole("button", { name: "Pin this view" });
    expect(document.querySelectorAll("[data-lens-row=pin]")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Show recent steps" })).toBeInTheDocument();
  });

  it("40 pins and very long names stay in one scrolling list, a name is cut with an ellipsis, not wrapped", async () => {
    const many = Array.from({ length: 40 }, (_, i) => ({ id: `v${i}`, name: i === 0 ? "A very long pinned view name ".repeat(6) : `View ${i}` }));
    mount(fakeServer({ views: many }));
    await userEvent.click(pins());
    await screen.findByRole("button", { name: /^View 39/ });
    expect(document.querySelectorAll("[data-lens-row=pin]")).toHaveLength(40);
    const long = document.querySelector("[data-lens-row=pin] span.truncate") as HTMLElement;
    expect(long.className).toContain("truncate");
    expect(long.className).toContain("max-w-[120px]");
  });

  it("the lens grows the hovered row and less its neighbours, and lets go when the pointer leaves", async () => {
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

  it("'...' renames the opened view and unpins it (PATCH, DELETE)", async () => {
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

  it("Recent unfolds the last steps, newest first", async () => {
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

  it("Agent falls back to the browser's chat when the server has no sessions (404), and resumes it in the dock", async () => {
    sessionStorage.setItem("kbchat.chat", JSON.stringify({ id: "kb-chat:1", session: null, messages: [{ role: "user", content: "Is parity hard?", sources: [] }, { role: "assistant", content: "Yes." }] }));
    mount();
    await userEvent.click(agent());
    const card = await screen.findByRole("button", { name: /Is parity hard/ });
    await userEvent.click(card);
    expect(useChatDock.getState().open).toBe(true);
  });

  it("Agent lists the server's sessions when /api/sessions exists, and resumes one by loading its document", async () => {
    const server = fakeServer({ sessions: [{ id: "s1", title: "Parity chat", updated: new Date().toISOString() }] });
    const orig = server.f;
    const f = vi.fn(async (u: RequestInfo | URL, i?: RequestInit) => (String(u) === "/api/sessions/s1" ? new Response(JSON.stringify({ id: "s1", messages: [{ role: "user", content: "hi", sources: [] }] })) : orig(u, i)));
    mount({ ...server, f: f as unknown as typeof fetch });
    await userEvent.click(agent());
    await userEvent.click(await screen.findByRole("button", { name: /Parity chat/ }));
    await waitFor(() => expect(useChatDock.getState().open).toBe(true));
    expect(JSON.parse(sessionStorage.getItem("kbchat.chat")!)).toMatchObject({ id: "kb-chat:s1" });
  });

  it("with no notes or chats a quiet placeholder card says so", async () => {
    mount(fakeServer(), {}, { listThink: async () => ({ capture_note: "x", notes: [] }) });
    await userEvent.click(think());
    expect(await screen.findByText("No think notes yet")).toBeInTheDocument();
    await userEvent.click(agent());
    expect(await screen.findByText("No chats yet")).toBeInTheDocument();
  });

  it("'...' beside each fan offers New and Open full screen", async () => {
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

describe("legends", () => {
  it("pressing a type name in the types card hides or shows that type", async () => {
    mount();
    await userEvent.click(screen.getByRole("button", { name: /show page types/i }));
    const person = screen.getByRole("button", { name: /^Person/ });
    expect(person).toHaveAttribute("aria-pressed", "false"); // hidden by default: dimmed
    await userEvent.click(person);
    expect(useGraphUi.getState().shownTypes?.has("person")).toBe(true);
    await userEvent.click(screen.getByRole("button", { name: /^Topic/ }));
    expect(useGraphUi.getState().shownTypes?.has("topic")).toBe(false);
  });

  it("the types card has concepts on the left of the divider and sources on the right", async () => {
    mount();
    const card = screen.getByRole("group", { name: "Page types" });
    const [left, right] = [...card.children].filter((e) => e.tagName === "DIV") as HTMLElement[];
    expect(left!.querySelector("[data-type=topic]")).not.toBeNull();
    expect(right!.querySelector("[data-type=paper]")).not.toBeNull();
    expect(left!.querySelector("[data-type=paper]")).toBeNull();
    // the divider sits between the two groups
    expect(left!.nextElementSibling).toHaveAttribute("aria-hidden", "true");
    expect(left!.nextElementSibling!.nextElementSibling).toBe(right);
  });

  it("pressing the colour dots spreads them into names; pressing a name hides that colour", async () => {
    mount();
    const legend = screen.getByRole("group", { name: /colour legend/i });
    expect(legend).toHaveAttribute("data-open", "false");
    await userEvent.click(screen.getByRole("button", { name: /show colour names/i }));
    expect(legend).toHaveAttribute("data-open", "true");
    const row = within(legend).getAllByRole("button", { pressed: true })[0]!;
    const label = row.getAttribute("data-row")!;
    await userEvent.click(row);
    expect(useGraphUi.getState().hiddenKeys.has(label)).toBe(true);
    expect(row).toHaveAttribute("aria-pressed", "false");
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

