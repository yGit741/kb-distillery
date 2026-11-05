import { createMemoryHistory } from "@tanstack/react-router";
import { act, render, waitFor } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { withFlag } from "@/flags/testing";
import { useChatFull } from "@/features/graph/shell/chatFullStore";
import { useSparkPanel } from "@/features/graph/shell/sparkPanelStore";
import { useChatDock } from "@/features/graph/tools/chatDockStore";
import { mockDataSource } from "@/test/datasource";
import { chatStatus } from "./fixtures";

const ds = mockDataSource({
  getChatStatus: async () => chatStatus(),
  getChatPrompts: async () => ({ prompts: [] }) as never,
  getShareStatus: async () => ({ status: null, chip: null }),
  getGraphNodes: async () => [],
  getGraph: () => new Promise(() => {}),
});

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null); // jsdom has no canvas
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("{}", { status: 404 }));
  useChatFull.setState({ full: false });
  useSparkPanel.setState({ open: false });
  useChatDock.setState({ question: "" });
});
afterEach(() => vi.restoreAllMocks());

const open = async (path: string) => {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }), "");
  render(<App source={ds} router={router} />);
  await act(async () => {});
  return router;
};

describe("flag chat-full: the chat route is the graph with the full chat", () => {
  it("on: /chat/<id> and /chat?q= land on the graph with the chat param", () =>
    withFlag("chat-full", true, () =>
      withFlag("spark-chat", true, () =>
        withFlag("graph-shell", true, async () => {
          const deep = await open("/chat/kb-chat%3Aabc");
          await waitFor(() => expect(deep.state.location.pathname).toBe("/graph"));
          // the graph takes the param, opens the full chat and drops it from the address
          await waitFor(() => expect(useChatFull.getState().full).toBe(true));
          await waitFor(() => expect(useSparkPanel.getState().open).toBe(true));
          useChatFull.setState({ full: false });
          useSparkPanel.setState({ open: false });
          const plain = await open("/chat?q=hello&scope=s");
          await waitFor(() => expect(plain.state.location.pathname).toBe("/graph"));
          await waitFor(() => expect(useChatFull.getState().full).toBe(true));
          expect(useChatDock.getState().question).toBe("hello");
          expect(plain.state.location.search).toEqual({ scope: "s" });
        }),
      ),
    ));

  it("off: /chat/<id> is as unknown as any other address", () =>
    withFlag("chat-full", false, async () => {
      const router = await open("/chat/kb-chat%3Aabc");
      expect(router.state.location.pathname).toContain("/chat/kb-chat");
      expect(document.body.textContent).toContain("Not Found");
    }));

  it("off: /chat stays the chat screen", () =>
    withFlag("chat-full", false, async () => {
      const router = await open("/chat");
      expect(router.state.location.pathname).toBe("/chat");
    }));
});
