import { createMemoryHistory } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { PageCard, PageDetail, PageFlag, PageFlagFixReply, PageFlagRequest, PageIndex } from "@/api/types";
import { resetEmbed } from "@/app/embed";
import { resetAllVariants, setVariant } from "@/components/variants";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { placeToolbar } from "./SelectionToolbar";

const card = (id: string): PageCard => ({ id, title: `Title ${id}`, type: "idea", maturity: "", depth: "", areas: [], preview: "p", words: 10 });
const index: PageIndex = { generated_at: "t", pages: [card("claim")], links: [], wanted: [], wanted_total: 0 };
const detail: PageDetail = {
  card: card("claim"), path: "wiki/claim.md", frontmatter: {}, markdown: "# Title claim\n\nThe first claim is strong.\n\nSecond block.\n",
  backlinks: [], outbound: [], broken: [], suggested: [],
};
const flag = (over: Partial<PageFlag> = {}): PageFlag => ({
  id: "f1", block_at: 1, text: "The first claim is strong.", note: "too strong", created: "t", resolved_by: null, orphaned: false, ...over,
});

function open(opts: { flags?: PageFlag[]; added?: PageFlagRequest[]; fixes?: number[]; removed?: string[]; fix?: () => Promise<PageFlagFixReply> } = {}) {
  let rows = opts.flags ?? [];
  const ds: Partial<DataSource> = {
    listPages: async () => index,
    getPage: async () => detail,
    getPageSources: async () => ({ slug: "claim", sources: [], counts: { total: 0, raw: 0, pages: 0, external: 0, by_disposition: {} } }),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
    listPageFlags: async () => ({ slug: "claim", flags: rows }),
    addPageFlag: async (_s, body) => {
      opts.added?.push(body);
      const f = flag({ id: "new", text: body.text, note: body.note ?? "", block_at: body.block_at ?? null });
      rows = [...rows, f];
      return f;
    },
    deletePageFlag: async (_s, id) => {
      opts.removed?.push(id);
      rows = rows.filter((r) => r.id !== id);
    },
    fixPageFlags: async () => {
      opts.fixes?.push(1);
      if (opts.fix) return opts.fix();
      rows = rows.map((r) => ({ ...r, resolved_by: "p9" }));
      return { reply: "ok", proposal_id: "p9", hunks: 2, flag_ids: rows.map((r) => r.id), orphaned: [], skipped: [] };
    },
  };
  render(<App source={mockDataSource(ds)} router={createAppRouter(createMemoryHistory({ initialEntries: ["/pages/claim"] }), "")} />);
}

const on = (fn: () => Promise<void>) => withFlag("ui.proposals", true, () => withFlag("ui.page-flags", true, fn));

async function select(text: string) {
  const para = await screen.findByText(text);
  const range = document.createRange();
  range.selectNodeContents(para);
  vi.spyOn(window, "getSelection").mockReturnValue({
    toString: () => text, rangeCount: 1, anchorNode: para.firstChild, getRangeAt: () => range, removeAllRanges: () => undefined,
  } as unknown as Selection);
  fireEvent.mouseUp(document);
}

describe("Page flags (ui.page-flags)", () => {
  beforeEach(() => {
    localStorage.clear();
    resetAllVariants();
    resetEmbed();
  });
  afterEach(() => vi.restoreAllMocks());

  it("Mark inaccurate opens a note field; Enter posts the span, the note and its block", () =>
    on(async () => {
      const added: PageFlagRequest[] = [];
      open({ added });
      await select("The first claim is strong.");
      fireEvent.click(await screen.findByRole("button", { name: "Mark inaccurate" }));
      const note = screen.getByRole("textbox", { name: "What is inaccurate?" });
      fireEvent.change(note, { target: { value: "  too strong  " } });
      fireEvent.keyDown(note, { key: "Enter" });
      await waitFor(() => expect(added).toHaveLength(1));
      expect(added[0]).toEqual({ text: "The first claim is strong.", note: "too strong", block_at: expect.any(Number) });
      await waitFor(() => expect(screen.getByTestId("flags-header")).toHaveTextContent("1 flagged"));
      expect(screen.queryByRole("toolbar", { name: "Selection" })).toBeNull();
    }));

  it("Escape cancels the note without posting", () =>
    on(async () => {
      const added: PageFlagRequest[] = [];
      open({ added });
      await select("The first claim is strong.");
      fireEvent.click(await screen.findByRole("button", { name: "Mark inaccurate" }));
      fireEvent.keyDown(screen.getByRole("textbox", { name: "What is inaccurate?" }), { key: "Escape" });
      expect(screen.queryByRole("toolbar", { name: "Selection" })).toBeNull();
      expect(added).toHaveLength(0);
    }));

  it("the three looks: underline and tint draw over the words, margin puts a flag beside the block with the note in a popover", () =>
    on(async () => {
      const removed: string[] = [];
      setVariant("page-flag-mark", "underline");
      open({ flags: [flag()], removed });
      await screen.findByText("The first claim is strong.");
      const marks = await screen.findByTestId("flag-marks");
      await waitFor(() => expect(marks.querySelectorAll(".flag-wave").length).toBeGreaterThan(0));
      expect(marks).toHaveAttribute("data-look", "underline");
      setVariant("page-flag-mark", "tint");
      await waitFor(() => expect(screen.getByTestId("flag-marks")).toHaveAttribute("data-look", "tint"));
      expect(screen.getByTestId("flag-marks").querySelector(".bg-warn\\/25")).not.toBeNull();
      expect(screen.getByTestId("flag-marks").querySelector(".flag-wave")).toBeNull();
      setVariant("page-flag-mark", "margin");
      const marker = await screen.findByRole("button", { name: "Flag: too strong" });
      fireEvent.click(marker);
      const pop = await screen.findByRole("dialog", { name: "Flag" });
      expect(pop).toHaveTextContent("too strong");
      fireEvent.click(within(pop).getByRole("button", { name: "Remove" }));
      await waitFor(() => expect(removed).toEqual(["f1"]));
      await waitFor(() => expect(screen.queryByRole("button", { name: /^Flag:/ })).toBeNull());
    }));

  it("underline: pointing at the flagged words shows the note", () =>
    on(async () => {
      setVariant("page-flag-mark", "underline");
      open({ flags: [flag()] });
      const article = (await screen.findByText("The first claim is strong.")).closest("article")!;
      await waitFor(() => expect(screen.getAllByTestId("flag-mark").length).toBeGreaterThan(0));
      fireEvent.mouseMove(article, { clientX: 0, clientY: 0 });
      expect(await screen.findByRole("dialog", { name: "Flag" })).toHaveTextContent("too strong");
    }));

  it("the default look is tint", () =>
    on(async () => {
      open({ flags: [flag()] });
      expect(await screen.findByTestId("flag-marks")).toHaveAttribute("data-look", "tint");
    }));

  for (const look of ["underline", "margin", "tint"] as const) {
    it(`${look}: a selection starting inside a flagged span gives the toolbar, never the note; a plain click or hover gives the note`, () =>
      on(async () => {
        setVariant("page-flag-mark", look);
        open({ flags: [flag()] });
        const article = (await screen.findByText("The first claim is strong.")).closest("article")!;
        await waitFor(() => expect(screen.getAllByTestId("flag-mark").length).toBeGreaterThan(0));
        // a drag over the flagged words: button held while moving, then a selection
        fireEvent.mouseMove(article, { clientX: 0, clientY: 0, buttons: 1 });
        expect(screen.queryByRole("dialog", { name: "Flag" })).toBeNull();
        await select("The first claim is strong.");
        fireEvent.mouseMove(article, { clientX: 0, clientY: 0 });
        expect(await screen.findByRole("toolbar", { name: "Selection" })).toBeInTheDocument();
        expect(screen.queryByRole("dialog", { name: "Flag" })).toBeNull();
        vi.restoreAllMocks();
        if (look === "margin") return;
        // without a selection, a plain click on the words opens the note
        fireEvent.click(article, { clientX: 0, clientY: 0 });
        expect(await screen.findByRole("dialog", { name: "Flag" })).toHaveTextContent("too strong");
      }));
  }

  it("Fix all flagged posts once and shows the proposal link; it is disabled with a reason when nothing is flagged", () =>
    on(async () => {
      const fixes: number[] = [];
      open({ flags: [flag(), flag({ id: "f2", text: "Second block.", note: "dated" })], fixes });
      const head = await screen.findByTestId("flags-header");
      await waitFor(() => expect(head).toHaveTextContent("2 flagged"));
      fireEvent.click(within(head).getByRole("button", { name: "Fix all flagged" }));
      const link = await screen.findByTestId("flags-proposal-link");
      expect(fixes).toHaveLength(1);
      expect(link).toHaveTextContent("Review the proposal (2 hunks)");
      expect(link.getAttribute("href")).toContain("/proposals/p9");
      await waitFor(() => expect(head).toHaveTextContent("0 flagged"));
      const btn = within(head).getByRole("button", { name: "Fix all flagged" });
      expect(btn).toBeDisabled();
      expect(btn.parentElement).toHaveAttribute("title", expect.stringContaining("Nothing is flagged"));
    }));

  it("while a fix is pending the button is disabled and says why", () =>
    on(async () => {
      let done: (r: PageFlagFixReply) => void = () => undefined;
      open({ flags: [flag()], fix: () => new Promise((res) => (done = res)) });
      const head = await screen.findByTestId("flags-header");
      await waitFor(() => expect(head).toHaveTextContent("1 flagged"));
      fireEvent.click(within(head).getByRole("button", { name: "Fix all flagged" }));
      await waitFor(() => expect(within(head).getByRole("button", { name: "Fix all flagged" })).toBeDisabled());
      expect(head).toHaveTextContent("Preparing one proposal");
      done({ reply: "Nothing to change.", proposal_id: null, hunks: 0, flag_ids: [], orphaned: [], skipped: [] });
      expect(await within(head).findByText("Nothing to change.")).toBeInTheDocument();
    }));

  it("is absent with the flag off", () =>
    withFlag("ui.page-flags", false, async () => {
      open({ flags: [flag()] });
      await screen.findByText("The first claim is strong.");
      expect(screen.queryByTestId("flags-header")).toBeNull();
      expect(screen.queryByTestId("flag-marks")).toBeNull();
    }));
});

describe("placeToolbar", () => {
  const size = { w: 200, h: 30 };
  const view = { w: 1000, h: 700 };
  it("goes below the selection, never over the line above it", () => {
    const at = placeToolbar({ left: 300, top: 200, width: 100, height: 20 }, size, view)!;
    expect(at.top).toBeGreaterThanOrEqual(220);
    expect(at.left).toBe(250);
  });
  it("flips above, clear of the selection, when there is no room below", () => {
    const at = placeToolbar({ left: 300, top: 660, width: 100, height: 20 }, size, view)!;
    expect(at.top + size.h).toBeLessThanOrEqual(660);
  });
  it("stays inside the viewport sideways and hides when scrolled away", () => {
    expect(placeToolbar({ left: 0, top: 100, width: 10, height: 20 }, size, view)!.left).toBe(8);
    expect(placeToolbar({ left: 990, top: 100, width: 10, height: 20 }, size, view)!.left).toBe(792);
    expect(placeToolbar({ left: 0, top: -100, width: 10, height: 20 }, size, view)).toBeNull();
  });
});
