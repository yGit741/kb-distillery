import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ChatList } from "./ChatList";

const sessions = Array.from({ length: 11 }, (_, i) => ({
  id: `s${i}`,
  title: `Chat ${i}`,
  created: "2026-11-03T10:00:00Z",
  updated: "2026-11-03T10:00:00Z",
}));

function mount(ui: React.ReactElement) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response(JSON.stringify({ sessions }), { headers: { "Content-Type": "application/json" } }));
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

afterEach(() => vi.restoreAllMocks());

describe("ChatList with a limit (the recent chats of a new chat)", () => {
  it("lists only the newest chats, without its own New chat button, and offers the rest", async () => {
    const onMore = vi.fn();
    mount(<ChatList activeId="kb-chat:none" server limit={8} onMore={onMore} />);
    expect(await screen.findByText("Chat 0")).toBeInTheDocument();
    expect(screen.getByText("Chat 7")).toBeInTheDocument();
    expect(screen.queryByText("Chat 8")).toBeNull();
    expect(screen.queryByRole("button", { name: /new chat/i })).toBeNull();
    await userEvent.click(screen.getByTestId("all-chats"));
    expect(onMore).toHaveBeenCalledTimes(1);
  });

  it("always shows a pinned chat, even past the limit", async () => {
    sessions.push({ id: "old-pin", title: "Pinned old chat", created: "2026-10-01T10:00:00Z", updated: "2026-10-01T10:00:00Z", pinned: true } as never);
    try {
      mount(<ChatList activeId="kb-chat:none" server limit={8} onMore={() => {}} />);
      expect(await screen.findByText("Pinned old chat")).toBeInTheDocument();
      expect(screen.getByText("Chat 6")).toBeInTheDocument();
      expect(screen.queryByText("Chat 7")).toBeNull();
    } finally {
      sessions.pop();
    }
  });

  it("has no All chats button when every chat fits", async () => {
    mount(<ChatList activeId="kb-chat:none" server limit={20} onMore={() => {}} />);
    expect(await screen.findByText("Chat 10")).toBeInTheDocument();
    expect(screen.queryByTestId("all-chats")).toBeNull();
  });
});
