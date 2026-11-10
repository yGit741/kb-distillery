import { createMemoryHistory } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { PageCard, PageDetail, PageIndex, PageChatRequest } from "@/api/types";
import { resetEmbed } from "@/app/embed";
import { setVariant } from "@/components/variants";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";

const card = (id: string): PageCard => ({ id, title: `Title ${id}`, type: "idea", maturity: "", depth: "", areas: [], preview: "p", words: 10 });
const index: PageIndex = { generated_at: "t", pages: [card("claim"), card("beta")], links: [], wanted: [], wanted_total: 0 };
const detail: PageDetail = {
  card: card("claim"), path: "wiki/claim.md", frontmatter: {}, markdown: "# Title claim\n\nThe first claim is strong.\n\nSecond block.\n",
  backlinks: [], outbound: [], broken: [], suggested: [],
};

function open(sent: PageChatRequest[] = [], reply?: () => Promise<never>) {
  const ds: Partial<DataSource> = {
    listPages: async () => index,
    getPage: async () => detail,
    getPageSources: async () => ({ slug: "claim", sources: [], counts: { total: 0, raw: 0, pages: 0, external: 0, by_disposition: {} } }),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
    getPageChat: async () => ({ slug: "claim", messages: [] }),
    searchMentions: async (q) => (q && "beta".startsWith(q) ? [{ slug: "beta", title: "Title beta" }] : []),
    postPageChat: async (_slug, body) => {
      sent.push(body);
      if (reply) return reply();
      return { reply: "Softened the claim.", proposal_id: "p1", hunks: 2, skipped: [{ before: "x", reason: "text not found on the page" }], unknown_mentions: [] };
    },
  };
  render(<App source={mockDataSource(ds)} router={createAppRouter(createMemoryHistory({ initialEntries: ["/pages/claim"] }), "")} />);
}

const on = (fn: () => Promise<void>) => withFlag("ui.proposals", true, () => withFlag("ui.page-chat", true, fn));

describe("Page chat (ui.page-chat)", () => {
  beforeEach(() => {
    localStorage.clear();
    resetEmbed();
  });

  it("composer: @ picker inserts a chip, chips can be removed, Enter sends the payload and shows the proposal card", () =>
    on(async () => {
      setVariant("page-chat-entry", "rail");
      const sent: PageChatRequest[] = [];
      open(sent);
      fireEvent.click(await screen.findByRole("button", { name: "Discuss this page" }));
      const panel = await screen.findByRole("complementary", { name: "Page chat" });
      const box = within(panel).getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;
      fireEvent.change(box, { target: { value: "soften this @be", selectionStart: 15 } });
      expect(await within(panel).findByRole("option", { name: /@beta/ })).toBeInTheDocument();
      fireEvent.keyDown(box, { key: "Enter" });
      expect(within(panel).getByTestId("mention-chip")).toHaveTextContent("beta");
      expect(box.value).toBe("soften this ");
      expect(sent).toHaveLength(0);
      fireEvent.click(within(panel).getByRole("button", { name: "Remove @beta" }));
      expect(within(panel).queryByTestId("mention-chip")).toBeNull();
      fireEvent.change(box, { target: { value: "soften @be", selectionStart: 10 } });
      await within(panel).findByRole("option", { name: /@beta/ }).then(() => fireEvent.keyDown(box, { key: "Enter" }));
      fireEvent.change(box, { target: { value: "soften this\nplease", selectionStart: 18 } });
      fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
      expect(sent).toHaveLength(0);
      fireEvent.keyDown(box, { key: "Enter" });
      await waitFor(() => expect(sent).toHaveLength(1));
      expect(sent[0]).toEqual({ message: "soften this\nplease", selections: [], mentions: ["beta"] });
      const cardLink = await within(panel).findByTestId("proposal-card");
      expect(cardLink).toHaveTextContent("Proposal: 2 hunks, 1 skipped");
      expect(cardLink.getAttribute("href")).toContain("/proposals/p1");
    }));

  it("gutter: clicking the margin icon adds a block chip that can be removed; errors are inline and keep the draft", () =>
    on(async () => {
      setVariant("page-chat-entry", "gutter");
      const sent: PageChatRequest[] = [];
      open(sent, () => Promise.reject(new Error("model busy")));
      const para = await screen.findByText("The first claim is strong.");
      fireEvent.mouseMove(para);
      fireEvent.click(await screen.findByRole("button", { name: "Ask about this block" }));
      const panel = await screen.findByRole("complementary", { name: "Page chat" });
      expect(within(panel).getByTestId("selection-chip")).toHaveTextContent("The first claim is strong.");
      const box = within(panel).getByRole("textbox", { name: "Message" });
      fireEvent.change(box, { target: { value: "soften", selectionStart: 6 } });
      fireEvent.keyDown(box, { key: "Enter" });
      await waitFor(() => expect(sent).toHaveLength(1));
      expect(sent[0]!.selections).toEqual([{ block_at: expect.any(Number), text: "The first claim is strong." }]);
      expect(await within(panel).findByRole("alert")).toHaveTextContent("model busy");
      expect((box as HTMLTextAreaElement).value).toBe("soften");
      fireEvent.click(within(panel).getByRole("button", { name: "Remove selection" }));
      expect(within(panel).queryByTestId("selection-chip")).toBeNull();
    }));

  it("entry variants switch: bubble, rail, selection and command each show their own entry", () =>
    on(async () => {
      setVariant("page-chat-entry", "bubble");
      open();
      expect(await screen.findByRole("button", { name: "Ask about this page" })).toBeInTheDocument();
      setVariant("page-chat-entry", "rail");
      expect(await screen.findByRole("button", { name: "Discuss this page" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Ask about this page" })).toBeNull();
      setVariant("page-chat-entry", "selection");
      expect(await screen.findByRole("button", { name: "Chat" })).toBeInTheDocument();
      setVariant("page-chat-entry", "command");
      expect(await screen.findByText("to ask")).toBeInTheDocument();
      fireEvent.keyDown(window, { key: "/" });
      expect(await screen.findByRole("dialog", { name: "Page command bar" })).toBeInTheDocument();
    }));

  it("is absent with the flag off", () =>
    withFlag("ui.page-chat", false, async () => {
      setVariant("page-chat-entry", "bubble");
      open();
      await screen.findByText("The first claim is strong.");
      expect(screen.queryByRole("button", { name: "Ask about this page" })).toBeNull();
    }));
});
