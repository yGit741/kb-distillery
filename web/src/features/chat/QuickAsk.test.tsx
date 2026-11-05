import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, Outlet, RouterProvider } from "@tanstack/react-router";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type ChatRequest, type DataSource } from "@/api";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { useUi } from "@/app/ui-store";
import { withFlag } from "@/flags/testing";
import { SEARCH } from "@/routes/search";
import { mockDataSource } from "@/test/datasource";
import { useAskHost } from "./askHost";
import { ChatScreen } from "./ChatScreen";
import { chatStatus } from "./fixtures";
import QuickAsk, { quickSendOptions } from "./QuickAsk";

/** A fake /api/chat: frames are pushed by the test; never a real model. */
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

const PROMPTS = [{ id: "query", title: "Query", description: "d", text: "base prompt" }];

/** A shell like the app's: the quick ask beside the outlet. `start` is "/" (no chat screen) or "/chat". */
function setup(start: "/" | "/chat") {
  const calls: { body: ChatRequest; stream: ReturnType<typeof fakeStream> }[] = [];
  const ds = mockDataSource({
    getChatStatus: async () => chatStatus(),
    getChatPrompts: async () => ({ prompts: PROMPTS }),
    listScopes: async () => ({ scopes: [] }),
    chatStream: async (body, signal) => {
      const stream = fakeStream(signal);
      calls.push({ body, stream });
      return stream.response;
    },
  });
  const root = createRootRoute({
    component: () => (
      <>
        <button type="button">elsewhere</button>
        <Outlet />
        <QuickAsk />
      </>
    ),
  });
  const home = createRoute({ getParentRoute: () => root, path: "/", component: () => <p>home screen</p> });
  const chat = createRoute({ getParentRoute: () => root, path: "/chat", validateSearch: SEARCH.chat, component: ChatScreen });
  const router = createRouter({ routeTree: root.addChildren([home, chat]), history: createMemoryHistory({ initialEntries: [start] }) });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { calls, router };
}

const cmdJ = () => fireEvent.keyDown(window, { key: "j", metaKey: true });
const dialog = () => screen.queryByRole("dialog", { name: "Quick ask" });

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
  act(() => {
    useUi.setState({ askOpen: false });
    useAskHost.setState({ host: null });
  });
});

describe("quick ask, agent-mode off", () => {
  it("Cmd-J does nothing: no composer, and the key is left alone", () =>
    withFlag("agent-mode", false, async () => {
      setup("/");
      await screen.findByText("home screen");
      const ev = new KeyboardEvent("keydown", { key: "j", metaKey: true, cancelable: true, bubbles: true });
      window.dispatchEvent(ev);
      expect(ev.defaultPrevented).toBe(false);
      expect(dialog()).toBeNull();
      expect(screen.queryByLabelText("Ask your knowledge base")).toBeNull();
    }));
});

describe("quick ask, agent-mode on", () => {
  it("Cmd-J opens a focused one-line composer anywhere; Esc closes and focus goes back", () =>
    withFlag("agent-mode", true, async () => {
      setup("/");
      await screen.findByText("home screen");
      expect(dialog()).toBeNull();
      const other = screen.getByRole("button", { name: "elsewhere" });
      other.focus();
      cmdJ();
      const box = await screen.findByRole("textbox", { name: "Ask your knowledge base" });
      expect(dialog()).toBeInTheDocument();
      await waitFor(() => expect(box).toHaveFocus());
      expect(box.tagName).toBe("INPUT");
      fireEvent.keyDown(window, { key: "Escape" });
      await waitFor(() => expect(dialog()).toBeNull());
      expect(other).toHaveFocus();
      // Ctrl-J works too (not a Mac), Cmd-Shift-J does not
      fireEvent.keyDown(window, { key: "J", metaKey: true, shiftKey: true });
      expect(dialog()).toBeNull();
      fireEvent.keyDown(window, { key: "j", ctrlKey: true });
      expect(await screen.findByRole("dialog", { name: "Quick ask" })).toBeInTheDocument();
    }));

  it("off the chat screen: sends with the main composer's options, shows the answer's lines, Open in chat lands in the same chat", () =>
    withFlag("agent-mode", true, async () => {
      window.localStorage.setItem("kbchat.model", JSON.stringify("m1"));
      const { calls, router } = setup("/");
      await screen.findByText("home screen");
      cmdJ();
      const user = userEvent.setup();
      await user.type(await screen.findByRole("textbox", { name: "Ask your knowledge base" }), "what is rank?{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0]!.body).toMatchObject({ question: "what is rank?", model: "m1", backend: "agent", auth_mode: "api_key", active_key: "personal", system: "base prompt" });
      const s = calls[0]!.stream;
      expect(await screen.findByText("Thinking…")).toBeInTheDocument();
      const open = screen.getByRole("button", { name: "Open in chat" });
      expect(open).toBeDisabled(); // the chat is stored when the answer is done
      s.push("session", { id: "sess-1" });
      s.push("delta", "Rank is the smallest number of terms.");
      expect(await screen.findByText("Rank is the smallest number of terms.")).toBeInTheDocument();
      expect(screen.getByText("what is rank?")).toBeInTheDocument();
      s.push("usage", { input_tokens: 1, output_tokens: 1 });
      s.push("done", {});
      s.end();
      await waitFor(() => expect(screen.getByRole("button", { name: "Open in chat" })).toBeEnabled());
      await user.click(screen.getByRole("button", { name: "Open in chat" }));
      await waitFor(() => expect(router.state.location.pathname).toBe("/chat"));
      expect(dialog()).toBeNull();
      // the chat screen shows the same turn, and continues the same agent session
      expect(await screen.findByLabelText("Conversation")).toHaveTextContent("Rank is the smallest number of terms.");
      await user.type(await screen.findByRole("textbox", { name: "Your message" }), "again{Enter}");
      await waitFor(() => expect(calls).toHaveLength(2));
      expect(calls[1]!.body.session).toBe("sess-1");
      expect(calls[1]!.body.history).toHaveLength(2);
    }));

  it("Esc while an answer runs hides the panel but lets the answer finish", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup("/");
      await screen.findByText("home screen");
      cmdJ();
      await userEvent.setup().type(await screen.findByRole("textbox", { name: "Ask your knowledge base" }), "q{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      fireEvent.keyDown(window, { key: "Escape" });
      await waitFor(() => expect(dialog()).toBeNull());
      expect(calls[0]!.body.question).toBe("q");
      calls[0]!.stream.push("delta", "late answer");
      calls[0]!.stream.push("done", {});
      calls[0]!.stream.end();
      cmdJ();
      expect(await screen.findByText("late answer")).toBeInTheDocument();
    }));

  it("an open panel is not asked twice when the chat screen comes and goes", () =>
    withFlag("agent-mode", true, async () => {
      const { calls, router } = setup("/");
      await screen.findByText("home screen");
      cmdJ();
      await userEvent.setup().type(await screen.findByRole("textbox", { name: "Ask your knowledge base" }), "once{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("delta", "answer");
      calls[0]!.stream.push("done", {});
      calls[0]!.stream.end();
      await screen.findByText("answer");
      await act(() => router.navigate({ to: "/chat" as "/" }));
      await screen.findByRole("textbox", { name: "Your message" });
      await act(() => router.navigate({ to: "/" }));
      await screen.findByText("home screen");
      await new Promise((r) => setTimeout(r, 300));
      expect(calls).toHaveLength(1);
      // and the panel still takes a new question
      expect(screen.getByRole("textbox", { name: "Ask your knowledge base" })).toBeEnabled();
    }));

  it("on the chat screen: the question goes through the screen's own session and the answer streams into the chat", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup("/chat");
      await screen.findByRole("textbox", { name: "Your message" });
      cmdJ();
      const user = userEvent.setup();
      await user.type(await screen.findByRole("textbox", { name: "Ask your knowledge base" }), "quick one{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0]!.body).toMatchObject({ question: "quick one", backend: "agent", system: "base prompt" });
      calls[0]!.stream.push("delta", "from the stream");
      // once in the open chat, once in the quick answer
      await waitFor(() => expect(screen.getAllByText("from the stream")).toHaveLength(2));
      expect(screen.getByLabelText("Conversation")).toHaveTextContent("quick one");
      // the main composer's draft is untouched by a quick ask
      expect(screen.getByRole("textbox", { name: "Your message" })).toHaveValue("");
      calls[0]!.stream.push("done", {});
      calls[0]!.stream.end();
    }));

  it("on the chat screen the card is centred over the column beside the plan rail, not over the rail", () =>
    withFlag("agent-mode", true, async () => {
      setup("/chat");
      await screen.findByRole("textbox", { name: "Your message" });
      cmdJ();
      const card = await screen.findByRole("dialog", { name: "Quick ask" });
      // the plan card sits in a 20rem rail at the right (from lg): the card shifts left by half of it and narrows by the rail
      expect(card.className).toContain("lg:left-[calc(50%-10rem)]");
      expect(card.className).toContain("lg:w-[min(36rem,calc(100vw-26rem))]");
    }));

  it("off the chat screen the card stays centred in the window", () =>
    withFlag("agent-mode", true, async () => {
      setup("/");
      await screen.findByText("home screen");
      cmdJ();
      const card = await screen.findByRole("dialog", { name: "Quick ask" });
      expect(card.className).not.toContain("lg:left-[calc(50%-10rem)]");
    }));
});

describe("quick ask in the app shell", () => {
  const ds: DataSource = mockDataSource({
    getLifecycle: () => new Promise(() => {}),
    getOps: () => new Promise(() => {}),
    getHealth: () => new Promise(() => {}),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
  });
  const shell = () => render(<App source={ds} router={createAppRouter(createMemoryHistory({ initialEntries: ["/app/system"] }))} />);

  it("flag off: the shell mounts nothing and leaves Cmd-J to the browser", () =>
    withFlag("agent-mode", false, async () => {
      shell();
      await screen.findByRole("navigation", { name: "Main" });
      const ev = new KeyboardEvent("keydown", { key: "j", metaKey: true, cancelable: true, bubbles: true });
      window.dispatchEvent(ev);
      expect(ev.defaultPrevented).toBe(false);
      expect(dialog()).toBeNull();
    }));

  it("flag on: Cmd-J opens it on any screen", () =>
    withFlag("agent-mode", true, async () => {
      shell();
      await screen.findByRole("navigation", { name: "Main" });
      await waitFor(() => {
        cmdJ();
        expect(dialog()).toBeInTheDocument(); // the lazy chunk may still be loading
      });
    }));
});

describe("quickSendOptions", () => {
  it("follows the browser's template, edits and model like the main composer", () => {
    window.localStorage.setItem("kbchat.template", JSON.stringify("learn"));
    window.localStorage.setItem("kbchat.edits", JSON.stringify({ learn: "my teach prompt" }));
    const prompts = [...PROMPTS, { id: "learn", title: "Learn", description: "", text: "teach" }];
    const o = quickSendOptions(chatStatus(), prompts);
    expect(o).toMatchObject({ model: "m1", backend: "agent", scope: "", system: "my teach prompt", label: "Learn" });
  });
});
