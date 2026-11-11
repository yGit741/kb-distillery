import { act, fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { withFlag } from "@/flags/testing";
import { EditPreviewHost } from "./Host";
import { useEditPreview } from "./store";

const sheet = () => screen.queryByTestId("edit-preview");
const group = (name: string) => within(screen.getByRole("region", { name }));
const apply = () => screen.getByRole("button", { name: /^Apply \d+ changes?$/ });

describe("edit preview sheet", () => {
  beforeEach(() => act(() => useEditPreview.getState().reset()));

  it("ui.edit-preview off: nothing is mounted, a link or a dropped file opens nothing", () => {
    withFlag("ui.edit-preview", false, () => {
      render(<EditPreviewHost preview="sample" />);
      fireEvent.drop(window, { dataTransfer: { types: ["Files"] } });
      expect(sheet()).toBeNull();
      expect(useEditPreview.getState().open).toBe(false);
    });
  });

  it("ui.edit-preview on: the link opens the sheet on all changes, with the queue, the graph and Apply held back", async () => {
    await withFlag("ui.ingest", false, () => withFlag("ui.edit-preview", true, async () => {
      render(<EditPreviewHost preview="sample" />);
      expect(await screen.findByRole("dialog", { name: "Scaling laws for sparse attention" })).toBeInTheDocument();
      expect(within(screen.getByRole("navigation", { name: "Queue" })).getAllByRole("listitem")).toHaveLength(5);
      expect(screen.getByRole("group", { name: "Pages this touches" })).toBeInTheDocument();
      for (const name of ["Before you start", "Needs a look", "Additions", "Links and fixes", "Left out"]) expect(screen.getByRole("region", { name })).toBeInTheDocument();
      expect(screen.getByText("13 still open")).toBeInTheDocument();
      expect(apply()).toBeDisabled();
    }));
  });

  it("clears the easy groups in bulk, decides the rest in the page, then applies", async () => {
    await withFlag("ui.ingest", false, () => withFlag("ui.edit-preview", true, async () => {
      const user = userEvent.setup();
      render(<EditPreviewHost preview="sample" />);
      await user.click(await screen.findByRole("button", { name: "Accept all 3" }));
      await user.click(screen.getByRole("button", { name: "Accept all 6" }));
      expect(screen.getByText("4 still open")).toBeInTheDocument();
      // a rewrite has no Accept in the list: it opens in the page
      expect(group("Needs a look").queryByRole("button", { name: "Accept" })).toBeNull();
      await user.click(group("Needs a look").getAllByRole("button", { name: "Open" })[0]!);

      // the protected page: one change is focused with its source, and the page holds until each is decided
      expect(screen.getByRole("heading", { name: /Attention/, level: 2 })).toBeInTheDocument();
      expect(screen.getByText(/Section 4\.2/)).toBeInTheDocument();
      const next = screen.getByRole("button", { name: "Next page" });
      expect(next).toBeDisabled();
      await user.click(screen.getByRole("button", { name: "Accept" }));
      await user.click(within(screen.getByTestId("change-a2")).getByRole("button", { name: "Reject" }));
      expect(next).toBeDisabled();
      await user.click(screen.getByRole("button", { name: "Accept all" }));
      expect(next).toBeEnabled();
      await user.click(next);

      // an ordinary page: one button accepts what is left and moves on
      expect(screen.getByRole("heading", { name: "Scaling laws", level: 2 })).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Accept the rest and continue" }));
      expect(screen.getByText(/Everything is decided/)).toBeInTheDocument();
      await user.click(screen.getByRole("button", { name: "Apply 12 changes" }));
      expect(screen.getByRole("heading", { name: "Nothing was written" })).toBeInTheDocument();
    }));
  });

  it("a dropped file opens the sheet reading, and closing keeps the decisions", async () => {
    await withFlag("ui.ingest", false, () => withFlag("ui.edit-preview", true, async () => {
      const user = userEvent.setup();
      render(<EditPreviewHost />);
      expect(sheet()).toBeNull();
      fireEvent.drop(window, { dataTransfer: { types: ["Files"] } });
      expect(await screen.findByRole("status")).toHaveTextContent("Reading the source");
      act(() => useEditPreview.getState().ready());
      await user.click(await screen.findByRole("button", { name: "Accept all 3" }));
      await user.click(screen.getByRole("button", { name: "Close" }));
      expect(sheet()).toBeNull();
      act(() => useEditPreview.getState().show());
      expect(await screen.findByText("10 still open")).toBeInTheDocument();
    }));
  });
});
