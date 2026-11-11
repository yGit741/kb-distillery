import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import type { ChatMessage } from "@/features/chat/thread";
import { useGraphUi } from "../store";
import { useChatFull } from "./chatFullStore";
import { CitesButton } from "./CitesButton";
import { useThinking } from "./thinkingStore";

const answer = { role: "assistant", content: "See [Margin](idea-margin.md) and [Rank](tensor-rank.md), again [Margin](idea-margin.md)." } as ChatMessage;

describe("the sources button on an answer", () => {
  beforeEach(() => {
    useGraphUi.setState({ readerSlug: null });
    useChatFull.setState({ pages: [{ id: "idea-margin", title: "Margin" }, { id: "tensor-rank", title: "Tensor rank" }], mention: null });
  });

  it("counts the cited pages and lists them in citation order; a click opens the page and keeps the list open", async () => {
    render(<CitesButton message={answer} />);
    await userEvent.click(screen.getByRole("button", { name: "2 sources" }));
    const list = screen.getByTestId("cites-list");
    const rows = within(list).getAllByRole("button");
    expect(rows.map((r) => r.textContent)).toEqual(["1Margin", "2Tensor rank"]);
    await userEvent.hover(rows[1]!);
    expect(useThinking.getState().hot).toBe("tensor-rank");
    await userEvent.click(rows[1]!);
    expect(useGraphUi.getState().readerSlug).toBe("tensor-rank");
    expect(screen.getByTestId("cites-list")).toBeInTheDocument();
    await userEvent.dblClick(rows[0]!);
    expect(useChatFull.getState().mention?.id).toBe("idea-margin");
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByTestId("cites-list")).not.toBeInTheDocument();
  });

  it("shows nothing on an answer that cites no page", () => {
    const { container } = render(<CitesButton message={{ role: "assistant", content: "No links here." } as ChatMessage} />);
    expect(container).toBeEmptyDOMElement();
  });
});
