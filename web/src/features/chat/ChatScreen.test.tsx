import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type ChatRequest, type DataSource } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { SEARCH } from "@/routes/search";
import { ChatScreen } from "./ChatScreen";
import { chatStatus } from "./fixtures";

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
    ping: () => ctl.enqueue(enc.encode(": ping\n\n")),
    end: () => ctl.close(),
  };
}

function setup(over: Partial<DataSource> = {}, url = "/chat") {
  const calls: { body: ChatRequest; signal?: AbortSignal; stream: ReturnType<typeof fakeStream> }[] = [];
  const ds = mockDataSource({
    getChatStatus: async () => chatStatus(),
    getChatPrompts: async () => ({ prompts: [{ id: "query", title: "Query", description: "d", text: "base prompt" }, { id: "learn", title: "Learn", description: "", text: "teach" }] }),
    listScopes: async () => ({ scopes: [{ slug: "scope-rl", title: "RL basics", status: "open", files: 3, digested: 1, uncovered: 2, coverage: 0.33 }] }),
    chatStream: async (body, signal) => {
      const stream = fakeStream(signal);
      calls.push({ body, signal, stream });
      return stream.response;
    },
    ...over,
  });
  const root = createRootRoute();
  const chat = createRoute({ getParentRoute: () => root, path: "/chat", validateSearch: SEARCH.chat, component: ChatScreen });
  const page = createRoute({ getParentRoute: () => root, path: "/pages/$slug", component: () => <p>page view</p> });
  const router = createRouter({ routeTree: root.addChildren([chat, page]), history: createMemoryHistory({ initialEntries: [url] }) });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const { unmount } = render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { calls, router, unmount };
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
});

const box = () => screen.findByRole("textbox", { name: "Your message" });

describe("ChatScreen", () => {
  it("shows loading, then the backend chip and the examples", async () => {
    setup();
    expect(await screen.findByRole("status", { name: /loading chat/i })).toBeInTheDocument();
    expect(await screen.findByTestId("backend-chip")).toHaveTextContent("Agent · API key personal sk-ant-…abcd");
    expect(screen.getByText("Teach me tensor rank")).toBeInTheDocument();
  });

  it("shows an error with retry when the service is unreachable", async () => {
    setup({ getChatStatus: async () => { throw new Error("down"); } });
    expect(await screen.findByRole("alert")).toHaveTextContent("The chat service is unreachable");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("streams an answer: deltas, [[slug]] links, tool trace, sources, usage; ignores pings", async () => {
    const { calls } = setup();
    const user = userEvent.setup();
    await user.type(await box(), "what is rank?{Enter}");
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]!.body).toMatchObject({ question: "what is rank?", model: "m1", backend: "agent", auth_mode: "api_key", active_key: "personal", system: "base prompt" });
    const s = calls[0]!.stream;
    s.ping();
    s.push("session", { id: "sess-1" });
    s.push("tool", { name: "Read", summary: "read tensor-rank", id: "t1" });
    s.push("sources", { hits: [{ slug: "tensor-rank", score: 1, summary: "rank of a tensor", in_context: false }], new: ["tensor-rank"] });
    s.push("delta", "Rank is $r$, see [[tensor-rank]]");
    expect(await screen.findByText(/read tensor-rank/)).toBeInTheDocument();
    const links = await screen.findAllByRole("link", { name: "tensor-rank" });
    expect(links.length).toBeGreaterThanOrEqual(2); // the citation in the answer and the sources list
    for (const l of links) expect(l).toHaveAttribute("href", "/pages/tensor-rank");
    s.push("usage", { input_tokens: 100, output_tokens: 20, cost_usd: 0.01, model: "m1", num_turns: 2 });
    s.push("done", {});
    s.end();
    expect(await screen.findByText("100 in · 20 out · $0.010")).toBeInTheDocument();
    expect(screen.getByText(/1 step · 1 page read/)).toBeInTheDocument();
    expect(screen.getByText("rank of a tensor")).toBeInTheDocument();
    expect(await screen.findByText(/Query · m1 · agent, 2 turns/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Stop/ })).toBeNull();

    // the agent session id is sent back on the next turn
    await user.type(await box(), "again{Enter}");
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]!.body.session).toBe("sess-1");
    expect(calls[1]!.body.history).toHaveLength(2);
  });

  it("Stop aborts the stream and marks the answer stopped", async () => {
    const { calls } = setup();
    const user = userEvent.setup();
    await user.type(await box(), "hi{Enter}");
    await waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.stream.push("delta", "partial");
    await screen.findByText("partial");
    await user.click(screen.getByRole("button", { name: /Stop/ }));
    expect(calls[0]!.signal!.aborted).toBe(true);
    expect(await screen.findByText("stopped")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Send/ })).toBeInTheDocument();
  });

  it("leaving the screen aborts a running stream", async () => {
    const { calls, unmount } = setup();
    const user = userEvent.setup();
    await user.type(await box(), "hi{Enter}");
    await waitFor(() => expect(calls).toHaveLength(1));
    unmount();
    expect(calls[0]!.signal!.aborted).toBe(true);
  });

  it("shows a stream error event and keeps the failed question out of the next history", async () => {
    const { calls } = setup();
    const user = userEvent.setup();
    await user.type(await box(), "first{Enter}");
    await waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.stream.push("error", { error: "no API key" });
    calls[0]!.stream.end();
    expect(await screen.findByRole("alert")).toHaveTextContent("no API key");
    await user.type(await box(), "second{Enter}");
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]!.body.history).toEqual([]);
  });

  it("surfaces a rejected request (HTTP error) on the answer", async () => {
    setup({ chatStream: async () => { throw new Error("/api/chat answered 400"); } });
    const user = userEvent.setup();
    await user.type(await box(), "hi{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("answered 400");
  });

  it("regenerate re-asks the last question", async () => {
    const { calls } = setup();
    const user = userEvent.setup();
    await user.type(await box(), "q1{Enter}");
    await waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.stream.push("delta", "a1");
    calls[0]!.stream.end();
    await user.click(await screen.findByRole("button", { name: /Regenerate/ }));
    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls[1]!.body.question).toBe("q1");
    expect(calls[1]!.body.history).toEqual([]);
  });

  it("deep links: ?scope= preselects and is sent, ?q= prefills without sending", async () => {
    const { calls } = setup({}, "/chat?scope=scope-rl&q=hello%20there");
    const input = await box();
    expect(input).toHaveValue("hello there");
    expect(calls).toHaveLength(0);
    expect(await screen.findByRole("combobox", { name: "Scope" })).toHaveValue("scope-rl");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Send/ }));
    await waitFor(() => expect(calls[0]!.body.scope).toBe("scope-rl"));
  });

  it("a prompt edit shows the custom badge, is sent as the system prompt, and resets", async () => {
    const { calls } = setup();
    const user = userEvent.setup();
    await box();
    await user.click(screen.getByText("Prompt:"));
    const sys = screen.getByRole("textbox", { name: "System prompt" });
    await user.clear(sys);
    await user.type(sys, "mine");
    expect(screen.getByText("custom")).toBeInTheDocument();
    await user.type(await box(), "go{Enter}");
    await waitFor(() => expect(calls[0]!.body.system).toBe("mine"));
    await user.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.queryByText("custom")).toBeNull();
    expect(sys).toHaveValue("base prompt");
  });

  it("keys are shown as hints only; adding a key posts it and the password field clears", async () => {
    const added: unknown[] = [];
    setup({ addChatKey: async (b) => { added.push(b); return chatStatus(); } });
    const user = userEvent.setup();
    await screen.findByTestId("backend-chip");
    expect(document.body.textContent).not.toContain("sk-ant-api03");
    await user.click(screen.getAllByText("Add or remove an API key")[0]!);
    await user.type(screen.getAllByLabelText("Name")[0]!, "work");
    const secret = screen.getAllByLabelText("Key")[0]! as HTMLInputElement;
    expect(secret.type).toBe("password");
    await user.type(secret, "sk-ant-api03-secret");
    await user.click(screen.getAllByRole("button", { name: "Add and use" })[0]!);
    await waitFor(() => expect(added).toEqual([{ name: "work", key: "sk-ant-api03-secret" }]));
    await waitFor(() => expect(secret).toHaveValue(""));
  });

  it("changing the backend and account posts settings", async () => {
    const sent: unknown[] = [];
    setup({ updateChatSettings: async (b) => { sent.push(b); return chatStatus(); } });
    const user = userEvent.setup();
    await screen.findByTestId("backend-chip");
    await user.selectOptions(screen.getAllByRole("combobox", { name: "Backend" })[0]!, "direct");
    await waitFor(() => expect(sent).toContainEqual({ backend: "direct" }));
  });

  it("saves the chat to the inbox and shows the path", async () => {
    const saved: unknown[] = [];
    const { calls } = setup({ saveChat: async (b) => { saved.push(b); return { path: "raw/inbox/q.md" }; } });
    const user = userEvent.setup();
    const save = await screen.findByRole("button", { name: /Save to inbox/ });
    expect(save).toBeDisabled();
    await user.type(await box(), "q{Enter}");
    await waitFor(() => expect(calls).toHaveLength(1));
    calls[0]!.stream.push("delta", "answer");
    calls[0]!.stream.end();
    await waitFor(() => expect(save).toBeEnabled());
    await user.click(save);
    expect(await screen.findByText("Saved to raw/inbox/q.md")).toBeInTheDocument();
    expect(saved[0]).toMatchObject({ title: "q", messages: [{ role: "user" }, { role: "assistant", content: "answer" }] });
  });

  it("New chat clears the thread", async () => {
    const { calls } = setup();
    const user = userEvent.setup();
    await user.type(await box(), "q{Enter}");
    await waitFor(() => expect(calls).toHaveLength(1));
    await user.click(screen.getByRole("button", { name: /New chat/ }));
    expect(within(document.body).queryByRole("list", { name: "Conversation" })).toBeNull();
    expect(calls[0]!.signal!.aborted).toBe(true); // a running answer is stopped
  });
});
