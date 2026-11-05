import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { DataSourceProvider } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { setSkillSelection } from "./skillsSelection";
import { useChatSession } from "./useChatSession";

const opts = { model: "m1", backend: "agent" as const, scope: "", system: "", auth: { auth_mode: "subscription" }, label: "Query" };

function run() {
  const chatStream = vi.fn(async () => new Response(new ReadableStream({ start: (c) => c.close() }), { headers: { "Content-Type": "text/event-stream" } }));
  const ds = mockDataSource({ chatStream, putSession: async () => ({}) as never });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <DataSourceProvider source={ds}>{children}</DataSourceProvider>
    </QueryClientProvider>
  );
  return { chatStream, ...renderHook(() => useChatSession(), { wrapper }) };
}

const sent = (chatStream: ReturnType<typeof run>["chatStream"]) => (chatStream.mock.calls[0] as unknown as [Record<string, unknown>])[0];

describe("the chat request carries the session's skills", () => {
  beforeEach(() => localStorage.clear());

  it("flag on: the subset chosen for this chat rides with the question", async () => {
    await withFlag("agent-mode", true, async () => {
      const { chatStream, result, unmount } = run();
      setSkillSelection(result.current.chat.id, ["query-knowledge"]);
      act(() => result.current.send("hi", opts));
      await waitFor(() => expect(chatStream).toHaveBeenCalled());
      expect(sent(chatStream).skills).toEqual(["query-knowledge"]);
      expect(sent(chatStream).skills_session).toBe(result.current.chat.id.replace("kb-chat:", ""));
      unmount();
      setSkillSelection(result.current.chat.id, undefined);
    });
  });

  it("flag off: no skills key at all", async () => {
    await withFlag("agent-mode", false, async () => {
      const { chatStream, result, unmount } = run();
      setSkillSelection(result.current.chat.id, ["query-knowledge"]);
      act(() => result.current.send("hi", opts));
      await waitFor(() => expect(chatStream).toHaveBeenCalled());
      expect(sent(chatStream).skills).toBeUndefined();
      expect(sent(chatStream).skills_session).toBeUndefined();
      unmount();
      setSkillSelection(result.current.chat.id, undefined);
    });
  });
});
