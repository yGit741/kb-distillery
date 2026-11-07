import { createMemoryHistory, createRootRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { withFlag } from "@/flags/testing";
import { MessageList } from "./MessageList";
import type { ChatMessage } from "./thread";

const noop = () => {};
const answer: ChatMessage = {
  role: "assistant",
  content: "| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nprint(1)\n```\n\nSee [Rank](tensor-rank.md) and [Web](https://example.com/x).",
  thinking: "weighing the options",
  thinkSecs: 7,
  thinkStart: 0,
  trace: [
    { name: "Read", summary: "read tensor-rank", id: "1", status: "done", result: "the page text" },
    { name: "Grep", summary: "grep rank", id: "2", status: "error", error: true, result: "boom" },
    { name: "Bash", summary: "query", id: "3", status: "running" },
  ],
};
const messages: ChatMessage[] = [{ role: "user", content: "q" }, answer];

/** The list renders page links, so it needs a router around it. */
async function renderList(list: ChatMessage[] = messages, busy = false) {
  const root = createRootRoute({ component: () => <MessageList messages={list} busy={busy} onRegenerate={noop} onAnswer={noop} /> });
  const router = createRouter({ routeTree: root, history: createMemoryHistory({ initialEntries: ["/"] }) });
  const out = render(<RouterProvider router={router} />);
  await screen.findByLabelText("Conversation");
  return out;
}

describe("MessageList transcript (agent-mode on)", () => {
  it("renders a collapsed thinking block labelled with its duration", () =>
    withFlag("agent-mode", true, async () => {
      await renderList();
      const think = screen.getByTestId("thinking") as HTMLDetailsElement;
      expect(think.open).toBe(false);
      expect(within(think).getByText("Thought for 7s")).toBeInTheDocument();
      await userEvent.setup().click(within(think).getByText("Thought for 7s"));
      expect(think.open).toBe(true);
      expect(screen.getByText("weighing the options")).toBeVisible();
    }));

  it("says Thinking… while the model still thinks", () =>
    withFlag("agent-mode", true, async () => {
      await renderList([messages[0]!, { ...answer, thinkSecs: undefined, content: "" }], true);
      expect(screen.getByText("Thinking…", { selector: "summary span" })).toBeInTheDocument();
    }));

  it("renders each tool as a one-liner with result, error and running states", () =>
    withFlag("agent-mode", true, async () => {
      await renderList();
      const lines = screen.getAllByTestId("tool-line");
      expect(lines).toHaveLength(3);
      expect(within(lines[0]!).getByText("read tensor-rank")).toBeInTheDocument();
      expect(within(lines[0]!).getByText("the page text")).toBeInTheDocument();
      expect(within(lines[1]!).getByLabelText("failed")).toBeInTheDocument();
      expect(lines[1]!.querySelector("summary")).toHaveClass("text-bad");
      expect(within(lines[2]!).getByLabelText("running")).toBeInTheDocument();
      expect(lines[2]!.querySelector("details")).toBeNull(); // no result yet: nothing to open
    }));

  it("renders tables, highlighted code and citation links", () =>
    withFlag("agent-mode", true, async () => {
      const { container } = await renderList();
      expect(screen.getByRole("table")).toBeInTheDocument();
      expect(container.querySelector("pre code.hljs, pre code.language-python")).not.toBeNull();
      const web = screen.getByRole("link", { name: "Web" });
      expect(web).toHaveAttribute("href", "https://example.com/x");
      expect(web).toHaveAttribute("rel", "noopener noreferrer");
    }));
});

describe("MessageList transcript (agent-mode off)", () => {
  it("keeps today's trace and shows no thinking block", () =>
    withFlag("agent-mode", false, async () => {
      await renderList();
      expect(screen.queryByTestId("thinking")).toBeNull();
      expect(screen.queryAllByTestId("tool-line")).toHaveLength(0);
      expect(screen.getByText(/3 steps · 1 page read/)).toBeInTheDocument();
    }));
});

describe("MessageList transcript with Show my thinking", () => {
  const withThinking = async (flag: boolean) => {
    const root = createRootRoute({
      component: () => (
        <MessageList messages={messages} busy={false} onRegenerate={noop} onAnswer={noop} thinking={flag ? () => <p>thinking section</p> : undefined} />
      ),
    });
    const router = createRouter({ routeTree: root, history: createMemoryHistory({ initialEntries: ["/"] }) });
    render(<RouterProvider router={router} />);
    await screen.findByLabelText("Conversation");
  };

  it("on: the per-tool lines are left out, the thinking block stays", () =>
    withFlag("agent-mode", true, async () => {
      await withThinking(true);
      expect(screen.queryAllByTestId("tool-line")).toHaveLength(0);
      expect(screen.getByTestId("thinking")).toBeInTheDocument();
    }));

  it("off: the per-tool lines stay", () =>
    withFlag("agent-mode", true, async () => {
      await withThinking(false);
      expect(screen.getAllByTestId("tool-line")).toHaveLength(3);
    }));
});
