import { createMemoryHistory } from "@tanstack/react-router";
import { configure, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { PageCard, PageDetail, PageIndex, RestructureBlocks, RestructureResult } from "@/api/types";
import { resetEmbed } from "@/app/embed";
import { setVariant } from "@/components/variants";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { parseSlash, pickRange, slashMatches, toggleCut } from "./lib";

// a cold page render is slow on a loaded machine (CI runs files in parallel)
vi.setConfig({ testTimeout: 90_000 });
configure({ asyncUtilTimeout: 30_000 });

const card = (id: string): PageCard => ({ id, title: `Title ${id}`, type: "idea", maturity: "", depth: "", areas: [], preview: "p", words: 10 });
const index: PageIndex = { generated_at: "t", pages: [card("claim"), card("beta")], links: [], wanted: [], wanted_total: 0 };
const detail: PageDetail = {
  card: card("claim"), path: "wiki/claim.md", frontmatter: {}, markdown: "# Title claim\n\nThe first claim is strong.\n\nSecond block.\n",
  backlinks: [], outbound: [], broken: [], suggested: [],
};
const blocks: RestructureBlocks = {
  slug: "claim", title: "Title claim", first: 2,
  blocks: [
    { index: 0, kind: "fm", text: "---\ntype: idea\n---\n" },
    { index: 1, kind: "prose", text: "\n" },
    { index: 2, kind: "heading", text: "# Title claim\n\n" },
    { index: 3, kind: "prose", text: "The first claim is strong.\n\n" },
    { index: 4, kind: "heading", text: "## Middle\n\n" },
    { index: 5, kind: "prose", text: "Middle text.\n\n" },
    { index: 6, kind: "prose", text: "Last words.\n" },
  ],
};
const made = (title: string): RestructureResult => ({ id: "p9", title, hunks: [{}, {}], ripple: [] }) as unknown as RestructureResult;

type Calls = { merge: unknown[]; split: unknown[]; extract: unknown[]; preview: string[] };

function open(calls: Calls, extra: Partial<DataSource> = {}) {
  const ds: Partial<DataSource> = {
    listPages: async () => index,
    getPage: async () => detail,
    getPageSources: async () => ({ slug: "claim", sources: [], counts: { total: 0, raw: 0, pages: 0, external: 0, by_disposition: {} } }),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
    getPageChat: async () => ({ slug: "claim", messages: [] }),
    searchMentions: async (q) => (q && "beta".startsWith(q) ? [{ slug: "beta", title: "Title beta" }] : []),
    getRestructureBlocks: async () => blocks,
    getMergePreview: async (slugs, survivor) => {
      calls.preview.push(`${slugs.join("+")}>${survivor}`);
      return { ripple: [{ slug: "ref", links: 3 }, { slug: "gamma", links: 1 }] };
    },
    restructureMerge: async (b) => (calls.merge.push(b), made("Merge beta into claim")),
    restructureSplit: async (b) => (calls.split.push(b), made("Split claim into 3 pages")),
    restructureExtract: async (b) => (calls.extract.push(b), made("Extract Middle from claim")),
    ...extra,
  };
  render(<App source={mockDataSource(ds)} router={createAppRouter(createMemoryHistory({ initialEntries: ["/pages/claim"] }), "")} />);
}

const fresh = (): Calls => ({ merge: [], split: [], extract: [], preview: [] });
const on = (fn: () => Promise<void>) => withFlag("ui.proposals", true, () => withFlag("ui.restructure", true, () => withFlag("ui.page-chat", true, fn)));

async function chooseFromMenu(item: string) {
  fireEvent.click(await screen.findByRole("button", { name: /Restructure/ }));
  fireEvent.click(await screen.findByRole("menuitem", { name: item }));
  return screen.findByRole("dialog");
}

describe("Restructure (ui.restructure)", () => {
  beforeEach(() => {
    localStorage.clear();
    resetEmbed();
  });

  it("is absent with the flag off", () =>
    withFlag("ui.proposals", true, () =>
      withFlag("ui.restructure", false, async () => {
        open(fresh());
        await screen.findByRole("heading", { name: /Title claim/ });
        expect(screen.queryByRole("button", { name: /Restructure/ })).toBeNull();
      }),
    ));

  it("merge dialog: pick a page, choose the survivor, see the ripple, post the payload, end on the proposal link", () =>
    on(async () => {
      const calls = fresh();
      open(calls);
      const dlg = await chooseFromMenu("Merge into…");
      fireEvent.change(within(dlg).getByRole("textbox", { name: "Add a page" }), { target: { value: "be" } });
      fireEvent.mouseDown(await within(dlg).findByRole("option", { name: /@beta/ }));
      expect(await within(dlg).findByTestId("ripple-summary")).toHaveTextContent("2 pages will have links rewritten to claim");
      expect(within(dlg).getByText(/ref · 3 links/)).toBeInTheDocument();
      fireEvent.click(within(dlg).getByRole("radio", { name: "Keep beta" }));
      await waitFor(() => expect(calls.preview).toContain("claim+beta>beta"));
      fireEvent.click(within(dlg).getByRole("button", { name: "Create proposal" }));
      const done = await within(dlg).findByTestId("restructure-done");
      expect(calls.merge).toEqual([{ slugs: ["claim", "beta"], survivor: "beta" }]);
      expect(within(done).getByRole("link")).toHaveAttribute("href", "/proposals/p9");
    }));

  it("split cut view: cuts are placed and removed, each piece is named, the payload is sorted", () =>
    on(async () => {
      const calls = fresh();
      open(calls);
      const dlg = await chooseFromMenu("Split…");
      await within(dlg).findByText("The first claim is strong.");
      expect(within(dlg).queryByText(/^---/)).toBeNull(); // front matter and the blank block are not listed
      const create = within(dlg).getByRole("button", { name: "Create proposal" });
      expect(create).toBeDisabled();
      fireEvent.click(within(dlg).getByRole("button", { name: "Cut before block 6" }));
      fireEvent.click(within(dlg).getByRole("button", { name: "Cut before block 4" }));
      expect(within(dlg).getAllByRole("textbox")).toHaveLength(2);
      fireEvent.click(within(dlg).getByRole("button", { name: "Remove the cut before block 6" }));
      expect(within(dlg).getAllByRole("textbox")).toHaveLength(1);
      fireEvent.click(within(dlg).getByRole("button", { name: "Cut before block 6" }));
      expect(create).toBeDisabled(); // unnamed pieces
      fireEvent.change(within(dlg).getByRole("textbox", { name: "Title of the page starting at block 6" }), { target: { value: "Closing" } });
      fireEvent.change(within(dlg).getByRole("textbox", { name: "Title of the page starting at block 4" }), { target: { value: "Middle part" } });
      fireEvent.click(create);
      await within(dlg).findByTestId("restructure-done");
      expect(calls.split).toEqual([{ slug: "claim", cuts: [4, 6], titles: ["Middle part", "Closing"] }]);
    }));

  it("extract posts the chosen block range and the title", () =>
    on(async () => {
      const calls = fresh();
      open(calls);
      const dlg = await chooseFromMenu("Extract…");
      fireEvent.click(await within(dlg).findByRole("button", { name: "Block 5" }));
      expect(within(dlg).getByText(/click the last block/)).toBeInTheDocument();
      fireEvent.click(within(dlg).getByRole("button", { name: "Block 4" }));
      expect(within(dlg).getByText("Blocks 4 to 5 will move.")).toBeInTheDocument();
      const create = within(dlg).getByRole("button", { name: "Create proposal" });
      expect(create).toBeDisabled();
      fireEvent.change(within(dlg).getByRole("textbox", { name: "Title of the new page" }), { target: { value: "Middle" } });
      fireEvent.click(create);
      await within(dlg).findByTestId("restructure-done");
      expect(calls.extract).toEqual([{ slug: "claim", from_at: 4, to_at: 5, title: "Middle" }]);
    }));

  it("command variant: no menu, /merge @beta in the page chat opens the merge dialog with beta picked", () =>
    on(async () => {
      setVariant("restructure-entry", "command");
      setVariant("page-chat-entry", "rail");
      open(fresh());
      fireEvent.click(await screen.findByRole("button", { name: "Discuss this page" }));
      expect(screen.queryByRole("button", { name: /Restructure/ })).toBeNull();
      const panel = await screen.findByRole("complementary", { name: "Page chat" });
      const box = within(panel).getByRole("textbox", { name: "Message" }) as HTMLTextAreaElement;
      fireEvent.change(box, { target: { value: "/", selectionStart: 1 } });
      expect(within(panel).getByRole("option", { name: /\/merge @page/ })).toBeInTheDocument();
      fireEvent.change(box, { target: { value: "/merge @be", selectionStart: 10 } });
      await within(panel).findByRole("option", { name: /@beta/ });
      fireEvent.keyDown(box, { key: "Enter" }); // picks @beta from the mention picker
      await within(panel).findByTestId("mention-chip");
      fireEvent.keyDown(box, { key: "Enter" }); // sends the command: it opens the dialog instead of the model
      const dlg = await screen.findByRole("dialog");
      expect(within(dlg).getByRole("radio", { name: "Keep beta" })).toBeInTheDocument();
      expect(within(dlg).getByRole("radio", { name: "Keep claim" })).toBeChecked();
    }));
});

describe("restructure lib", () => {
  it("parses slash commands and their mentions", () => {
    expect(parseSlash("/merge @beta @gamma", [])).toEqual({ kind: "merge", mentions: ["beta", "gamma"] });
    expect(parseSlash("/Split", [])).toEqual({ kind: "split", mentions: [] });
    expect(parseSlash("/extract", ["a"])).toEqual({ kind: "extract", mentions: ["a"] });
    expect(parseSlash("soften /merge", [])).toBeNull();
    expect(parseSlash("/mergeable", [])).toBeNull();
    expect(slashMatches("/s")).toEqual(["split"]);
    expect(slashMatches("hello")).toEqual([]);
  });
  it("toggles cuts and picks ranges", () => {
    expect(toggleCut([6], 4)).toEqual([4, 6]);
    expect(toggleCut([4, 6], 4)).toEqual([6]);
    const a = pickRange(null, 5);
    expect(a).toEqual({ from: 5, to: 5, open: true });
    expect(pickRange(a, 3)).toEqual({ from: 3, to: 5, open: false });
    expect(pickRange({ from: 3, to: 5, open: false }, 7)).toEqual({ from: 7, to: 7, open: true });
  });
});
