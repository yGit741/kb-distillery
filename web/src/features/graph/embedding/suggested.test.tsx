import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PinList } from "../shell/corners/PinList";
import { SUGGESTED } from "./store";

const props = { open: true, views: [], recent: [], suggest: "x", onApply: vi.fn(), onPin: vi.fn(), onRename: vi.fn(), onRecentOpen: vi.fn(), canApply: () => true };

describe("suggested embedding views in the pinned list", () => {
  it("shows dashed suggestions under their label, and a click applies the view", async () => {
    const onSuggest = vi.fn();
    render(<PinList {...props} suggested={SUGGESTED} onSuggest={onSuggest} />);
    expect(screen.getByText("Suggested from meaning")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Suggested view: Meaning map" }));
    expect(onSuggest).toHaveBeenCalledWith("map");
  });

  it("no suggestions: no section; a shared site never offers them", () => {
    const { unmount } = render(<PinList {...props} />);
    expect(screen.queryByText("Suggested from meaning")).toBeNull();
    unmount();
    render(<PinList {...props} readOnly suggested={SUGGESTED} />);
    expect(screen.queryByText("Suggested from meaning")).toBeNull();
  });
});
