import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type ChatRequest } from "@/api";
import { withFlag } from "@/flags/testing";
import { SEARCH } from "@/routes/search";
import { mockDataSource } from "@/test/datasource";
import { ChatScreen } from "./ChatScreen";
import { chatStatus } from "./fixtures";
import { PlanPanel } from "./PlanPanel";
import type { TodoItem } from "./sse";

/** jsdom has no layout: say whether the viewport is at the `lg` breakpoint. */
function viewport(wide: boolean) {
  const old = window.matchMedia;
  window.matchMedia = ((q: string) => ({
    matches: wide, media: q, onchange: null,
    addEventListener: () => {}, removeEventListener: () => {},
    addListener: () => {}, removeListener: () => {}, dispatchEvent: () => false,
  })) as typeof window.matchMedia;
  return () => { window.matchMedia = old; };
}

const items: TodoItem[] = [
  { content: "Read the pages", status: "completed" },
  { content: "Compare them", status: "in_progress" },
  { content: "Write the answer", status: "pending" },
];

describe("PlanPanel", () => {
  let restore = () => {};
  afterEach(() => restore());

  it("lists each item with its status as an icon and as text, and a count", () => {
    restore = viewport(true);
    render(<PlanPanel items={items} busy placement="rail" />);
    const panel = screen.getByTestId("plan-panel");
    expect(within(panel).getByText("1 of 3 done")).toBeInTheDocument();
    const rows = within(panel).getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-status"))).toEqual(["completed", "in_progress", "pending"]);
    expect(rows.map((r) => r.textContent)).toEqual(["done: Read the pages", "in progress: Compare them", "pending: Write the answer"]);
    expect(rows[0]).toHaveClass("line-through");
    expect(rows[1]).toHaveClass("font-medium");
    for (const r of rows) expect(r.querySelector("svg")).not.toBeNull();
  });

  it("collapses when empty, and when every step is done and the turn is over", () => {
    restore = viewport(true);
    const { container, rerender } = render(<PlanPanel items={[]} busy placement="rail" />);
    expect(container).toBeEmptyDOMElement();
    const allDone = items.map((t) => ({ ...t, status: "completed" as const }));
    rerender(<PlanPanel items={allDone} busy={false} placement="rail" />);
    expect(container).toBeEmptyDOMElement();
    rerender(<PlanPanel items={allDone} busy placement="rail" />);
    expect(screen.getByTestId("plan-panel")).toBeInTheDocument();
  });

  it("renders in one place: the rail when wide, the composer slot when narrow", () => {
    restore = viewport(true);
    const { container, rerender } = render(<><PlanPanel items={items} busy placement="rail" /><PlanPanel items={items} busy placement="inline" /></>);
    expect(container.querySelectorAll("[data-testid=plan-panel]")).toHaveLength(1);
    expect(screen.getByTestId("plan-panel")).toHaveAttribute("data-placement", "rail");
    restore();
    restore = viewport(false);
    rerender(<><PlanPanel items={items} busy placement="rail" /><PlanPanel items={items} busy placement="inline" /></>);
    expect(container.querySelectorAll("[data-testid=plan-panel]")).toHaveLength(1);
    expect(screen.getByTestId("plan-panel")).toHaveAttribute("data-placement", "inline");
  });
});

function fakeStream(signal?: AbortSignal) {
  const enc = new TextEncoder();
  let ctl!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({ start: (c) => (ctl = c) });
  signal?.addEventListener("abort", () => {
    try { ctl.close(); } catch { /* already closed */ }
  });
  return {
    response: new Response(body, { headers: { "Content-Type": "text/event-stream" } }),
    push: (event: string, data: unknown) => ctl.enqueue(enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)),
    end: () => ctl.close(),
  };
}

/** The chat screen with a fake /api/chat; the test pushes the frames. */
function setupChat() {
  const calls: { body: ChatRequest; stream: ReturnType<typeof fakeStream> }[] = [];
  const ds = mockDataSource({
    getChatStatus: async () => chatStatus(),
    getChatPrompts: async () => ({ prompts: [{ id: "query", title: "Query", description: "d", text: "base prompt" }] }),
    listScopes: async () => ({ scopes: [] }),
    chatStream: async (body, signal) => {
      const stream = fakeStream(signal);
      calls.push({ body, stream });
      return stream.response;
    },
  });
  const root = createRootRoute();
  const chat = createRoute({ getParentRoute: () => root, path: "/chat", validateSearch: SEARCH.chat, component: ChatScreen });
  const router = createRouter({ routeTree: root.addChildren([chat]), history: createMemoryHistory({ initialEntries: ["/chat"] }) });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return calls;
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

const box = () => screen.findByRole("textbox", { name: "Your message" });

describe("plan panel in the chat screen", () => {
  let restore = () => {};
  afterEach(() => restore());

  it("flag on, wide: sits in the session rail, follows each todo event, replaces the list, collapses when emptied", () =>
    withFlag("agent-mode", true, async () => {
      restore = viewport(true);
      const calls = setupChat();
      const user = userEvent.setup();
      await user.type(await box(), "go{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      const s = calls[0]!.stream;
      expect(screen.queryByTestId("plan-panel")).toBeNull(); // no plan yet: no panel, nothing reserved
      s.push("todo", { items: [{ content: "Read pages", status: "in_progress" }, { content: "Answer", status: "pending" }] });
      const panel = await screen.findByTestId("plan-panel");
      expect(panel.closest("aside")).not.toBeNull();
      expect(panel).toHaveAttribute("data-placement", "rail");
      expect(within(panel).getByText("0 of 2 done")).toBeInTheDocument();
      expect(within(panel).getByText("Read pages").closest("li")).toHaveAttribute("data-status", "in_progress");
      // the next event replaces the list
      s.push("todo", { items: [{ content: "Read pages", status: "completed" }, { content: "Answer", status: "in_progress" }, { content: "Cite", status: "pending" }] });
      await screen.findByText("1 of 3 done");
      expect(screen.getAllByTestId("plan-panel")).toHaveLength(1);
      expect(screen.getByText("Cite")).toBeInTheDocument();
      // an empty list collapses it
      s.push("todo", { items: [] });
      await waitFor(() => expect(screen.queryByTestId("plan-panel")).toBeNull());
    }));

  it("flag on, wide, with the narrow Session drawer open: still one plan in the page", () =>
    withFlag("agent-mode", true, async () => {
      restore = viewport(true);
      const calls = setupChat();
      const user = userEvent.setup();
      await user.type(await box(), "go{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("todo", { items: [{ content: "Read pages", status: "pending" }] });
      await screen.findByTestId("plan-panel");
      await user.click(screen.getByRole("button", { name: "Session" }));
      expect(screen.getAllByTestId("plan-panel")).toHaveLength(1);
    }));

  it("flag on, narrow: the plan keeps the composer slot", () =>
    withFlag("agent-mode", true, async () => {
      restore = viewport(false);
      const calls = setupChat();
      await userEvent.setup().type(await box(), "go{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("todo", { items: [{ content: "Read pages", status: "pending" }] });
      const panel = await screen.findByTestId("plan-panel");
      expect(panel).toHaveAttribute("data-placement", "inline");
      expect(panel.closest("aside")).toBeNull();
    }));

  it("flag off: no plan panel, and the rail is the plain one", () =>
    withFlag("agent-mode", false, async () => {
      restore = viewport(true);
      const calls = setupChat();
      await userEvent.setup().type(await box(), "go{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("todo", { items: [{ content: "Read pages", status: "pending" }] });
      calls[0]!.stream.push("delta", "hello");
      await screen.findByText("hello");
      expect(screen.queryByTestId("plan-panel")).toBeNull();
      expect(screen.getByRole("complementary", { name: "Session and sources" })).toHaveAttribute("class", "hidden lg:block");
    }));
});
