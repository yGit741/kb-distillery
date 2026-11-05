import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { DataSourceProvider, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { PastChats } from "./PastChats";
import { CHAT_KEY, MIGRATED_KEY, MIRROR_DELAY_MS } from "./serverStorage";
import { writeJson } from "./storage";
import { useChatSession } from "./useChatSession";
import type { Chat } from "./thread";

const stored: Chat = { id: "kb-chat:20261103101500-abc123", session: null, messages: [{ role: "user", content: "hi" }, { role: "assistant", content: "yo" }] };

function stream() {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      c.enqueue(enc.encode(`event: delta\ndata: ${JSON.stringify("answer")}\n\n`));
      c.enqueue(enc.encode(`event: usage\ndata: ${JSON.stringify({ cost_usd: 0.01 })}\n\n`));
      c.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

function setup(over: Partial<DataSource> = {}) {
  const putSession = vi.fn(async (id: string) => ({ id, title: "t", created: "", updated: "", messages: [], usage: { cost_usd: 0, turns: 0 } }) as never);
  const ds = mockDataSource({ chatStream: async () => stream(), putSession, ...over });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <DataSourceProvider source={ds}>{children}</DataSourceProvider>
    </QueryClientProvider>
  );
  return { ds, putSession, wrapper };
}

const opts = { model: "m1", backend: "agent" as const, scope: "", system: "", auth: { auth_mode: "subscription" }, label: "Query" };

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
});

describe("useChatSession with the agent-mode flag", () => {
  it("on: mirrors a finished turn to the server after the debounce, with model and backend", async () => {
    await withFlag("agent-mode", true, async () => {
      const { putSession, wrapper } = setup();
      const { result } = renderHook(() => useChatSession(), { wrapper });
      await waitFor(() => expect(localStorage.getItem(MIGRATED_KEY)).toBe("true"));
      expect(putSession).not.toHaveBeenCalled();
      act(() => result.current.send("What is tensor rank?", opts));
      await waitFor(() => expect(result.current.chat.messages[1]?.meta).toContain("m1"));
      expect(putSession).not.toHaveBeenCalled(); // debounced
      await waitFor(() => expect(putSession).toHaveBeenCalledTimes(1), { timeout: MIRROR_DELAY_MS * 4 });
      const [id, body] = putSession.mock.calls[0] as unknown as [string, { messages: { content: string }[]; model: string; backend: string }];
      expect(id).toBe(result.current.chat.id.replace("kb-chat:", ""));
      expect(body).toMatchObject({ model: "m1", backend: "agent" });
      expect(body.messages.map((m) => m.content)).toEqual(["What is tensor rank?", "answer"]);
    });
  });

  it("on: copies the browser-held chat once, then not again", async () => {
    await withFlag("agent-mode", true, async () => {
      writeJson("session", CHAT_KEY, stored);
      const { putSession, wrapper } = setup();
      const first = renderHook(() => useChatSession(), { wrapper });
      await waitFor(() => expect(putSession).toHaveBeenCalledTimes(1));
      expect(putSession.mock.calls[0]![0]).toBe("20261103101500-abc123");
      first.unmount();
      renderHook(() => useChatSession(), { wrapper });
      await waitFor(() => expect(localStorage.getItem(MIGRATED_KEY)).toBe("true"));
      expect(putSession).toHaveBeenCalledTimes(1);
    });
  });

  it("off: the browser path alone, no server call and no marker", async () => {
    await withFlag("agent-mode", false, async () => {
      writeJson("session", CHAT_KEY, stored);
      const { putSession, wrapper } = setup();
      const { result } = renderHook(() => useChatSession(), { wrapper });
      act(() => result.current.send("q", opts));
      await waitFor(() => expect(result.current.busy).toBe(false));
      await waitFor(() => expect(JSON.parse(sessionStorage.getItem(CHAT_KEY)!).messages).toHaveLength(4));
      await new Promise((r) => setTimeout(r, MIRROR_DELAY_MS + 200));
      expect(putSession).not.toHaveBeenCalled();
      expect(localStorage.getItem(MIGRATED_KEY)).toBeNull();
    });
  });
});

describe("PastChats", () => {
  const summary = (id: string, title: string) => ({ id, title, created: "2026-11-03T10:00:00Z", updated: "2026-11-03T10:00:00Z", turns: 2, cost_usd: 0.05, preview: "first question", status: "idle" as const });

  it("off: renders nothing and never lists", async () => {
    await withFlag("agent-mode", false, async () => {
      const listSessions = vi.fn();
      const { wrapper } = setup({ listSessions });
      const { container } = render(<PastChats />, { wrapper });
      expect(container).toBeEmptyDOMElement();
      expect(listSessions).not.toHaveBeenCalled();
    });
  });

  it("on: lists newest first as given, opens a chat into the session, renames and deletes", async () => {
    await withFlag("agent-mode", true, async () => {
      let sessions = [summary("s2", "Second chat"), summary("s1", "First chat")];
      const getSession = vi.fn(async (id: string) => ({ id, title: "x", created: "", updated: "", messages: [{ role: "user", content: "restored" }], usage: { cost_usd: 0, turns: 1 } }) as never);
      const renameSession = vi.fn(async (id: string, title: string) => {
        sessions = sessions.map((s) => (s.id === id ? { ...s, title } : s));
        return {} as never;
      });
      const deleteSession = vi.fn(async (id: string) => {
        sessions = sessions.filter((s) => s.id !== id);
        return { ok: true, id };
      });
      const { wrapper } = setup({ listSessions: async () => ({ sessions }), getSession, renameSession, deleteSession });
      const chatHook = renderHook(() => useChatSession(), { wrapper });
      render(<PastChats />, { wrapper });
      const items = await screen.findAllByRole("listitem");
      expect(items.map((li) => li.textContent)).toEqual([expect.stringContaining("Second chat"), expect.stringContaining("First chat")]);

      await userEvent.click(screen.getByRole("button", { name: "First chat" }));
      await waitFor(() => expect(chatHook.result.current.chat.id).toBe("kb-chat:s1"));
      expect(chatHook.result.current.chat.messages[0]?.content).toBe("restored");

      await userEvent.click(screen.getByRole("button", { name: "Rename Second chat" }));
      const input = screen.getByLabelText("Chat title");
      await userEvent.clear(input);
      await userEvent.type(input, "Renamed{Enter}");
      await waitFor(() => expect(renameSession).toHaveBeenCalledWith("s2", "Renamed"));
      expect(await screen.findByText("Renamed")).toBeInTheDocument();

      await userEvent.click(screen.getByRole("button", { name: "Delete Renamed" }));
      expect(deleteSession).not.toHaveBeenCalled();
      await userEvent.click(screen.getByRole("button", { name: "Delete chat" }));
      await waitFor(() => expect(deleteSession).toHaveBeenCalledWith("s2"));
      await waitFor(() => expect(screen.queryByText("Renamed")).not.toBeInTheDocument());
    });
  });
});
