import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type ChatMessageIn, type ChatRequest, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { SEARCH } from "@/routes/search";
import { mockDataSource } from "@/test/datasource";
import { ChatScreen } from "./ChatScreen";
import { chatStatus } from "./fixtures";

/** A fake /api/chat stream (frames pushed by the test) and a fake /api/chat/message; never a real model. */
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

function setup(over: Partial<DataSource> = {}) {
  const calls: { body: ChatRequest; signal?: AbortSignal; stream: ReturnType<typeof fakeStream> }[] = [];
  const messages: ChatMessageIn[] = [];
  const ds = mockDataSource({
    getChatStatus: async () => chatStatus(),
    getChatPrompts: async () => ({ prompts: [{ id: "query", title: "Query", description: "d", text: "base prompt" }] }),
    listScopes: async () => ({ scopes: [] }),
    chatStream: async (body, signal) => {
      const stream = fakeStream(signal);
      calls.push({ body, signal, stream });
      return stream.response;
    },
    sendChatMessage: async (b) => {
      messages.push(b);
      return { ok: true };
    },
    ...over,
  });
  const root = createRootRoute();
  const chat = createRoute({ getParentRoute: () => root, path: "/chat", validateSearch: SEARCH.chat, component: ChatScreen });
  const router = createRouter({ routeTree: root.addChildren([chat]), history: createMemoryHistory({ initialEntries: ["/chat"] }) });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { calls, messages };
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

const box = () => screen.findByRole("textbox", { name: "Your message" });

describe("chat transcript (agent-mode on)", () => {
  it("streams thinking, a tool line with its result and the todo list; the todo clears on the next turn", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await user.type(await box(), "go{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      const s = calls[0]!.stream;
      s.push("session", { id: "sess-1" });
      s.push("thinking", "pondering");
      s.push("tool", { name: "Grep", summary: "grep rank", id: "t1", status: "running" });
      s.push("tool", { name: "Grep", summary: "grep rank", id: "t1", status: "done", result: "3 hits" });
      s.push("todo", { items: [{ content: "Read pages", status: "in_progress" }, { content: "Answer", status: "pending" }] });
      expect(await screen.findByTestId("plan-panel")).toHaveTextContent("0 of 2 done");
      expect(await screen.findByText("pondering")).toBeInTheDocument();
      expect(screen.getByText("3 hits")).toBeInTheDocument();
      s.push("delta", "Done.");
      s.push("usage", { input_tokens: 1, output_tokens: 1 });
      s.push("done", {});
      s.end();
      expect(await screen.findByText(/Thought for \d+s/)).toBeInTheDocument();
      // every item still open: the list stays after the turn; a new turn starts a fresh one
      await user.type(await box(), "next{Enter}");
      await waitFor(() => expect(calls).toHaveLength(2));
      expect(screen.queryByTestId("plan-panel")).toBeNull();
    }));

  it("a message sent while the turn runs is queued, not restarted; the echo opens the next pair", () =>
    withFlag("agent-mode", true, async () => {
      const { calls, messages } = setup();
      const user = userEvent.setup();
      await user.type(await box(), "first{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("session", { id: "sess-1" });
      calls[0]!.stream.push("delta", "working");
      await screen.findByText("working");
      await user.type(await box(), "also X{Enter}");
      await waitFor(() => expect(messages).toEqual([{ session: "sess-1", text: "also X" }]));
      expect(calls).toHaveLength(1);
      expect(calls[0]!.signal!.aborted).toBe(false);
      calls[0]!.stream.push("user", { text: "also X" });
      expect(await screen.findByText("also X")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /Stop/ })).toBeInTheDocument();
    }));

  it("falls back to stop + resume when the message cannot be queued", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup({ sendChatMessage: async () => { throw new Error("404"); } });
      const user = userEvent.setup();
      await user.type(await box(), "first{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("session", { id: "sess-1" });
      calls[0]!.stream.push("delta", "working");
      await screen.findByText("working");
      await user.type(await box(), "change course{Enter}");
      await waitFor(() => expect(calls).toHaveLength(2));
      expect(calls[0]!.signal!.aborted).toBe(true);
      expect(calls[1]!.body).toMatchObject({ question: "change course", session: "sess-1" });
    }));

  it("Stop aborts the stream (the server interrupts the client)", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await user.type(await box(), "hi{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      await user.click(await screen.findByRole("button", { name: /Stop/ }));
      expect(calls[0]!.signal!.aborted).toBe(true);
      expect(await screen.findByText("stopped")).toBeInTheDocument();
    }));

  it("lists finished sessions and resumes one with its session id", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await user.type(await box(), "What is rank?{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      const s = calls[0]!.stream;
      s.push("session", { id: "sess-1" });
      s.push("delta", "A number.");
      s.push("usage", { input_tokens: 1, output_tokens: 1 });
      s.push("done", {});
      s.end();
      const item = await screen.findByRole("button", { name: /What is rank\?/ });
      expect(item).toHaveTextContent("just now");
      await user.click(screen.getAllByRole("button", { name: /New chat/ })[0]!);
      expect(screen.queryByText("A number.")).toBeNull();
      await user.click(await screen.findByRole("button", { name: /What is rank\?/ }));
      expect(await screen.findByText("A number.")).toBeInTheDocument();
      await user.type(await box(), "more{Enter}");
      await waitFor(() => expect(calls).toHaveLength(2));
      expect(calls[1]!.body.session).toBe("sess-1");
    }));
});

describe("chat transcript (agent-mode off)", () => {
  it("shows no recent-sessions list and no thinking, and a message while busy is ignored", () =>
    withFlag("agent-mode", false, async () => {
      const { calls, messages } = setup();
      const user = userEvent.setup();
      await user.type(await box(), "first{Enter}");
      await waitFor(() => expect(calls).toHaveLength(1));
      expect(screen.queryByText("Recent sessions")).toBeNull();
      await user.type(await box(), "second{Enter}");
      expect(messages).toEqual([]);
      expect(calls).toHaveLength(1);
    }));
});
