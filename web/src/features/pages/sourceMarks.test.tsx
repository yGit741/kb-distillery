import { createMemoryHistory } from "@tanstack/react-router";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { PageCard, PageDetail, PageIndex, PageSource, PageSources } from "@/api/types";
import { resetEmbed } from "@/app/embed";
import { setVariant } from "@/components/variants";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { numberSources, placePopover, remarkSourceMarks } from "./sourceMarks";

const card = (id: string): PageCard => ({ id, title: `Title ${id}`, type: "idea", maturity: "", depth: "", areas: [], preview: "p", words: 10 });
const index: PageIndex = { generated_at: "t", pages: [card("claim"), card("paper-p")], links: [], wanted: [], wanted_total: 0 };
const md = [
  "# Title claim",
  "",
  "## Evidence",
  "",
  "The [paper](paper-p.md) shows it. Raw: `raw/printed-docs/q.pdf`.",
  "",
  "## Other",
  "",
  "Plain words.",
  "",
  "```",
  "raw/printed-docs/z.pdf",
  "```",
  "",
  "## My notes",
  "",
  "[[paper-p]] and https://example.org/a again.",
  "",
].join("\n");
const detail: PageDetail = { card: card("claim"), path: "wiki/claim.md", frontmatter: {}, markdown: md, backlinks: [], outbound: [], broken: [], suggested: [] };
const src = (over: Partial<PageSource>): PageSource => ({
  id: "x", title: "X", kind: "pdf", format: "printed-docs", disposition: "source", path_rel: null, slug: null, url: null, route: null, via: ["sources"], cited_in_sections: [], added: null, ...over,
});
const sources: PageSource[] = [
  src({ id: "raw/printed-docs/p.pdf", title: "Paper P", path_rel: "raw/printed-docs/p.pdf", slug: "paper-p", cited_in_sections: ["Evidence", "My notes"], added: "2026-10-01" }),
  src({ id: "https://example.org/a", title: "example.org/a", kind: "web", format: "web-clips", disposition: "external", url: "https://example.org/a", cited_in_sections: ["My notes"] }),
  src({ id: "raw/printed-docs/q.pdf", title: "Paper Q", path_rel: "raw/printed-docs/q.pdf", cited_in_sections: ["Evidence"] }),
  src({ id: "raw/printed-docs/r.pdf", title: "Paper R", path_rel: "raw/printed-docs/r.pdf", cited_in_sections: ["Other"] }),
  src({ id: "raw/printed-docs/z.pdf", title: "Paper Z", path_rel: "raw/printed-docs/z.pdf", cited_in_sections: [] }),
];
const reply = (list: PageSource[]): PageSources => ({ slug: "claim", sources: list, counts: { total: list.length, raw: 0, pages: 0, external: 0, by_disposition: {} } });

function open(list: PageSource[]) {
  const ds: Partial<DataSource> = {
    listPages: async () => index,
    getPage: async () => detail,
    getPageSources: async () => reply(list),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
  };
  render(<App source={mockDataSource(ds)} router={createAppRouter(createMemoryHistory({ initialEntries: ["/pages/claim"] }), "")} />);
}
const on = (fn: () => Promise<void>) => withFlag("ui.page-sources", true, fn);

describe("numbered source markers", () => {
  beforeEach(() => {
    localStorage.clear();
    resetEmbed();
  });

  it("numbers the footer 1..n and puts [n] where the text cites the source, never in My notes", () =>
    on(async () => {
      setVariant("page-sources", "footer");
      open(sources);
      const footer = await screen.findByRole("region", { name: "Page sources" });
      expect(within(footer).getAllByTestId("source-number").map((e) => e.textContent)).toEqual(["1", "2", "3", "4", "5"]);
      const marks = await screen.findAllByTestId("source-marker");
      // 1: after the page link; 3: after the code span; 4: no mention in the text, so the end of its section heading
      expect(marks.map((m) => m.getAttribute("data-n"))).toEqual(["1", "3", "4"]);
      const article = footer.closest("article")!;
      expect(marks[0]!.closest("sup")!.previousElementSibling?.textContent).toBe("paper");
      expect(marks[1]!.closest("sup")!.previousElementSibling?.tagName).toBe("CODE");
      expect(marks[2]!.closest("h2")).toHaveTextContent("Other");
      // 2 is cited only in My notes, 5 only inside a code block: a number in the footer, no marker in the text
      expect(article.querySelector('[data-n="2"]')).toBeNull();
      expect(article.querySelector('[data-n="5"]')).toBeNull();
      // presentation only: the markers add no text to the page
      expect(article.textContent).not.toMatch(/\[\d\]/);
    }));

  it("hover and keyboard focus show the source; click jumps to its footer entry", () =>
    on(async () => {
      setVariant("page-sources", "footer");
      open(sources);
      const [first] = await screen.findAllByTestId("source-marker");
      expect(screen.queryByRole("dialog", { name: "Source 1" })).toBeNull();
      fireEvent.mouseEnter(first!);
      const pop = await screen.findByRole("dialog", { name: "Source 1" });
      expect(pop).toHaveTextContent("Paper P");
      expect(pop).toHaveTextContent("pdf · source · 2026-10-01");
      expect(pop).toHaveTextContent("Filed in printed-docs: raw/printed-docs/p.pdf");
      expect(within(pop).getByRole("link", { name: "Paper P" }).getAttribute("href")).toContain("/pipeline");
      fireEvent.keyDown(first!, { key: "Escape" });
      expect(screen.queryByRole("dialog", { name: "Source 1" })).toBeNull();
      fireEvent.blur(first!);
      act(() => first!.focus());
      expect(await screen.findByRole("dialog", { name: "Source 1" })).toBeInTheDocument();
      const entry = document.getElementById("page-source-1")!;
      fireEvent.click(first!);
      expect(entry).toHaveAttribute("data-flash");
      await waitFor(() => expect(entry).not.toHaveAttribute("data-flash"), { timeout: 3000 });
    }));

  it("a page whose sources are cited nowhere gets numbers in the footer and no markers", () =>
    on(async () => {
      setVariant("page-sources", "footer");
      open([sources[4]!]);
      expect(await screen.findByRole("region", { name: "Page sources" })).toBeInTheDocument();
      expect(screen.queryAllByTestId("source-marker")).toHaveLength(0);
    }));

  it("the side-tab and hover-marks variants get no markers and no numbers", () =>
    on(async () => {
      setVariant("page-sources", "hover-marks");
      open(sources);
      await screen.findByTestId("sources-count-mark");
      expect(screen.queryAllByTestId("source-marker")).toHaveLength(0);
      setVariant("page-sources", "side-tab");
      await screen.findByTestId("sources-side-tab");
      expect(screen.queryAllByTestId("source-marker")).toHaveLength(0);
      expect(screen.queryAllByTestId("source-number")).toHaveLength(0);
    }));
});

describe("pure parts", () => {
  it("numberSources counts from 1 in the endpoint's order", () => {
    expect(numberSources(sources).map((i) => [i.n, i.s.title])).toEqual([[1, "Paper P"], [2, "example.org/a"], [3, "Paper Q"], [4, "Paper R"], [5, "Paper Z"]]);
  });

  it("the plugin leaves a tree with no cited section untouched", () => {
    const tree = { type: "root", children: [{ type: "heading", depth: 2, children: [{ type: "text", value: "A" }] }, { type: "paragraph", children: [{ type: "text", value: "raw/printed-docs/p.pdf" }] }] };
    const before = JSON.stringify(tree);
    remarkSourceMarks(numberSources([sources[0]!].map((s) => ({ ...s, cited_in_sections: [] }))))()(tree as never);
    expect(JSON.stringify(tree)).toBe(before);
  });

  it("the popover goes below the cited block with a gap, above it near the bottom, and stays inside the window", () => {
    const size = { w: 288, h: 100 };
    const view = { w: 1000, h: 800 };
    const mid = placePopover({ left: 500, top: 380, bottom: 416, width: 20 }, size, view);
    expect(mid.below).toBe(true);
    expect(mid.top).toBeGreaterThanOrEqual(416 + 8);
    const low = placePopover({ left: 500, top: 740, bottom: 770, width: 20 }, size, view);
    expect(low.below).toBe(false);
    expect(low.top + size.h).toBeLessThanOrEqual(740 - 8);
    expect(placePopover({ left: 990, top: 400, bottom: 416, width: 10 }, size, view).left + size.w).toBeLessThanOrEqual(1000 - 8);
    expect(placePopover({ left: 0, top: 400, bottom: 416, width: 10 }, size, view).left).toBeGreaterThanOrEqual(8);
  });
});
