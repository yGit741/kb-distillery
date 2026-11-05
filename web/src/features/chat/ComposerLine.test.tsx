import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type ChatRequest, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { SEARCH } from "@/routes/search";
import { mockDataSource } from "@/test/datasource";
import { ChatScreen } from "./ChatScreen";
import { ContextRing } from "./ComposerLine";
import { initialComposer, useComposer } from "./composer";
import { chatStatus } from "./fixtures";

/** A fake /api/chat stream (frames pushed by the test); never a real model. */
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
    /** several frames in one network chunk, so they reach the handler as one batch */
    pushAll: (evs: [string, unknown][]) =>
      ctl.enqueue(enc.encode(evs.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join(""))),
    end: () => ctl.close(),
  };
}

function setup(over: Partial<DataSource> = {}) {
  const calls: { body: ChatRequest; signal?: AbortSignal; stream: ReturnType<typeof fakeStream> }[] = [];
  const ds = mockDataSource({
    getChatStatus: async () =>
      chatStatus({ models: [{ id: "m1", label: "Model One", context: 100000 }, { id: "m2", label: "Model Two" }], default_model: "m1" }),
    getChatPrompts: async () => ({ prompts: [{ id: "query", title: "Query", description: "d", text: "base prompt" }] }),
    listScopes: async () => ({ scopes: [] }),
    chatStream: async (body, signal) => {
      const stream = fakeStream(signal);
      calls.push({ body, signal, stream });
      return stream.response;
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
  return { calls };
}

beforeEach(() => {
  window.sessionStorage.clear();
  window.localStorage.clear();
  useComposer.setState(initialComposer());
});

const box = () => screen.findByRole("textbox", { name: "Your message" });
const line = () => screen.findByTestId("composer-line");
const send = async (user: ReturnType<typeof userEvent.setup>, text = "hi") => user.type(await box(), `${text}{Enter}`);
/** open a setting's menu and pick one of its choices */
async function pick(user: ReturnType<typeof userEvent.setup>, setting: string, choice: string) {
  await user.click(within(await line()).getByRole("button", { name: setting }));
  await user.click(await screen.findByRole("button", { name: new RegExp(`^${choice}`) }));
}

describe("composer line (agent-mode off)", () => {
  it("is not there and the request carries none of its picks", () =>
    withFlag("agent-mode", false, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      expect(screen.queryByTestId("composer-line")).toBeNull();
      expect(calls[0]!.body).not.toHaveProperty("effort");
      expect(calls[0]!.body).not.toHaveProperty("billing");
      expect(calls[0]!.body).not.toHaveProperty("budget");
    }));
});

describe("composer line (agent-mode on)", () => {
  it("reads as plain words with the defaults", () =>
    withFlag("agent-mode", true, async () => {
      setup();
      const l = await line();
      expect(l).toHaveTextContent(/^Model One\s*·\s*Medium\s*·\s*API\s*·\s*\$0\.50$/);
    }));

  it("sends the picks with the request and keeps them per browser", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await pick(user, "Model", "Model Two");
      await pick(user, "Effort", "Low");
      await pick(user, "Billing", "API");
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0]!.body).toMatchObject({ model: "m2", effort: "low", billing: "api" });
      expect(JSON.parse(window.localStorage.getItem("kbchat.composer")!)).toMatchObject({ effort: "low", billing: "api", cap: 0.5 });
      expect(await line()).toHaveTextContent(/^Model Two\s*·\s*Low\s*·\s*API\s*·\s*\$0\.50$/);
    }));

  it("sends no billing until one is picked: the Session account decides", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      expect(calls[0]!.body).toMatchObject({ effort: "medium" });
      expect(calls[0]!.body).not.toHaveProperty("billing");
    }));

  it("starts from the saved picks", () =>
    withFlag("agent-mode", true, async () => {
      window.localStorage.setItem("kbchat.composer", JSON.stringify({ effort: "max", billing: "batch", cap: 2 }));
      useComposer.setState(initialComposer());
      setup();
      expect(await line()).toHaveTextContent(/^Model One\s*·\s*Max\s*·\s*Batch\s*·\s*\$2\.00$/);
    }));

  it("pauses the stream when a turn's cost crosses the cap; Continue raises it by $0.50 and resumes", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      const s = calls[0]!.stream;
      s.push("delta", "before");
      s.push("usage", { input_tokens: 10, output_tokens: 5, cost_usd: 0.62 });
      expect(await screen.findByTestId("cap-prompt")).toHaveTextContent("Continue? (spent $0.62 of $0.50)");
      s.push("delta", " after");
      await new Promise((r) => setTimeout(r, 50));
      expect(screen.queryByText(/after/)).toBeNull();          // the stream is paused, not read on
      await user.click(screen.getByRole("button", { name: "Continue" }));
      expect(await screen.findByText(/after/)).toBeInTheDocument();
      expect(screen.queryByTestId("cap-prompt")).toBeNull();
      expect(calls[0]!.signal!.aborted).toBe(false);
      // a second charge in the same turn: 0.62 + 0.58 = 1.20 is over the raised cap of 1.00
      s.push("usage", { cost_usd: 0.58 });
      expect(await screen.findByTestId("cap-prompt")).toHaveTextContent("Continue? (spent $1.20 of $1.00)");
    }));

  it("Stop interrupts the turn the way the Stop button does", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("delta", "partial");
      calls[0]!.stream.push("usage", { est_cost_usd: 0.7, cost_usd: 0, billing: "subscription" });
      const alert = await screen.findByTestId("cap-prompt");
      await user.click(within(alert).getByRole("button", { name: "Stop" }));
      await waitFor(() => expect(calls[0]!.signal!.aborted).toBe(true));
      expect(await screen.findByText("stopped")).toBeInTheDocument();
      expect(screen.queryByTestId("cap-prompt")).toBeNull();
    }));

  it("Stop on the prompt still applies the rest of that batch (session id, sources) before it interrupts", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.pushAll([
        ["delta", "complete answer"],
        ["usage", { cost_usd: 0.9 }],
        ["session", { id: "sess-9" }],
        ["done", {}],
      ]);
      const prompt = await screen.findByTestId("cap-prompt");
      await user.click(within(prompt).getByRole("button", { name: "Stop" }));
      await waitFor(() => expect(calls[0]!.signal!.aborted).toBe(true));
      await waitFor(() => expect(screen.queryByTestId("cap-prompt")).toBeNull());
      await user.type(await box(), "next{Enter}");
      await waitFor(() => expect(calls).toHaveLength(2));
      expect(calls[1]!.body).toMatchObject({ session: "sess-9" });
    }));

  it("one Continue is enough for a turn far over the cap", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("usage", { cost_usd: 5 });
      expect(await screen.findByTestId("cap-prompt")).toHaveTextContent("spent $5.00 of $0.50");
      await user.click(screen.getByRole("button", { name: "Continue" }));
      calls[0]!.stream.push("delta", "carry on");
      expect(await screen.findByText("carry on")).toBeInTheDocument();
      expect(screen.queryByTestId("cap-prompt")).toBeNull();
    }));

  it("the composer Stop button also clears a waiting prompt", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("usage", { cost_usd: 0.9 });
      await screen.findByTestId("cap-prompt");
      await user.click(screen.getAllByRole("button", { name: /Stop/ }).find((b) => b.closest("form"))!);
      await waitFor(() => expect(screen.queryByTestId("cap-prompt")).toBeNull());
      expect(await screen.findByText("stopped")).toBeInTheDocument();
    }));

  it("no prompt under the cap or with no cap", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      calls[0]!.stream.push("usage", { cost_usd: 0.4 });
      calls[0]!.stream.push("delta", "fine");
      expect(await screen.findByText("fine")).toBeInTheDocument();
      expect(screen.queryByTestId("cap-prompt")).toBeNull();
      calls[0]!.stream.push("done", {});
      calls[0]!.stream.end();
      await pick(user, "Cost cap per turn", "No cap");
      await send(user, "again");
      await waitFor(() => expect(calls).toHaveLength(2));
      calls[1]!.stream.push("usage", { cost_usd: 25 });
      calls[1]!.stream.push("delta", "still here");
      expect(await screen.findByText("still here")).toBeInTheDocument();
      expect(screen.queryByTestId("cap-prompt")).toBeNull();
    }));

  it("the ring shows how much of the model's context the answer used", () =>
    withFlag("agent-mode", true, async () => {
      const { calls } = setup();
      const user = userEvent.setup();
      await send(user);
      await waitFor(() => expect(calls).toHaveLength(1));
      expect(screen.getByTestId("context-ring")).toHaveAttribute("data-fill", "0");
      calls[0]!.stream.push("usage", { input_tokens: 10000, cache_read_input_tokens: 15000, output_tokens: 3 });
      await waitFor(() => expect(screen.getByTestId("context-ring")).toHaveAttribute("data-fill", "25"));
      expect(screen.getByRole("img", { name: "Context about 25% used (25,000 of 100,000 tokens)" })).toBeInTheDocument();
    }));
});

describe("ContextRing", () => {
  it("clamps at full and shows an empty ring for no data", () => {
    const { rerender } = render(<ContextRing used={500} max={100} />);
    expect(screen.getByTestId("context-ring")).toHaveAttribute("data-fill", "100");
    rerender(<ContextRing used={0} max={0} />);
    expect(screen.getByTestId("context-ring")).toHaveAttribute("data-fill", "0");
  });
});
