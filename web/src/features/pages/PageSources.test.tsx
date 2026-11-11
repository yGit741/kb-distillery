import { createMemoryHistory } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { PageCard, PageDetail, PageIndex, PageSources } from "@/api/types";
import { resetEmbed } from "@/app/embed";
import { setVariant } from "@/components/variants";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";

const card = (id: string): PageCard => ({ id, title: `Title ${id}`, type: "idea", maturity: "", depth: "", areas: [], preview: "p", words: 10 });
const index: PageIndex = { generated_at: "t", pages: [card("claim")], links: [], wanted: [], wanted_total: 0 };
const detail: PageDetail = {
  card: card("claim"), path: "wiki/claim.md", frontmatter: {}, markdown: "# Title claim\n\n## Evidence\n\nText.\n\n## Other\n\nMore.\n",
  backlinks: [], outbound: [], broken: [], suggested: [],
};
const some: PageSources = {
  slug: "claim",
  counts: { total: 2, raw: 1, pages: 0, external: 1, by_disposition: { source: 1, external: 1 } },
  sources: [
    { id: "raw/printed-docs/p.pdf", title: "Paper P", kind: "pdf", format: "printed-docs", disposition: "source", path_rel: "raw/printed-docs/p.pdf", slug: "paper-p", url: null, route: "/pipeline?q=raw/printed-docs/p.pdf", via: ["sources"], cited_in_sections: ["Evidence"], added: "2026-10-01" },
    { id: "https://example.org/a", title: "example.org/a", kind: "web", format: "web-clips", disposition: "external", path_rel: null, slug: null, url: "https://example.org/a", route: null, via: ["sources"], cited_in_sections: [], added: null },
  ],
};
const none: PageSources = { slug: "claim", sources: [], counts: { total: 0, raw: 0, pages: 0, external: 0, by_disposition: {} } };

function open(sources: PageSources, calls: string[] = []) {
  const ds: Partial<DataSource> = {
    listPages: async () => index,
    getPage: async () => detail,
    getPageSources: async (slug) => (calls.push(slug), sources),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
  };
  render(<App source={mockDataSource(ds)} router={createAppRouter(createMemoryHistory({ initialEntries: ["/pages/claim"] }), "")} />);
}

describe("Sources on a page (ui.page-sources)", () => {
  beforeEach(() => {
    localStorage.clear();
    resetEmbed();
  });

  it("footer: a Sources section with title, format, disposition and a link to the raw item", () =>
    withFlag("ui.page-sources", true, async () => {
      setVariant("page-sources", "footer");
      open(some);
      const section = await screen.findByRole("region", { name: "Page sources" });
      expect(within(section).getByText("Paper P")).toBeInTheDocument();
      expect(within(section).getByText("source")).toBeInTheDocument();
      expect(within(section).getByText(/printed-docs · 2026-10-01 · cited in Evidence/)).toBeInTheDocument();
      expect(within(section).getByRole("link", { name: "Paper P" }).getAttribute("href")).toContain("/pipeline");
      expect(within(section).getByRole("link", { name: "example.org/a" }).getAttribute("href")).toBe("https://example.org/a");
    }));

  it("footer: a source named only by a link in the text says so", () =>
    withFlag("ui.page-sources", true, async () => {
      setVariant("page-sources", "footer");
      open({ ...some, sources: [{ ...some.sources[0]!, via: ["links"] }, { ...some.sources[1]!, via: ["sources", "links"] }] });
      const section = await screen.findByRole("region", { name: "Page sources" });
      expect(within(section).getByText(/printed-docs · 2026-10-01 · linked in the text · cited in Evidence/)).toBeInTheDocument();
      expect(within(section).getAllByText(/linked in the text/)).toHaveLength(1);
    }));

  it("footer: nothing is rendered without sources", () =>
    withFlag("ui.page-sources", true, async () => {
      setVariant("page-sources", "footer");
      const calls: string[] = [];
      open(none, calls);
      await waitFor(() => expect(calls).toEqual(["claim"]));
      await screen.findByText("Text.");
      expect(screen.queryByRole("region", { name: "Page sources" })).toBeNull();
    }));

  it("side-tab: a Sources tab that opens the panel; a disabled No sources tab when empty", () =>
    withFlag("ui.page-sources", true, async () => {
      setVariant("page-sources", "side-tab");
      open(some);
      const tab = await screen.findByRole("button", { name: "Sources · 2" });
      expect(tab).toHaveAttribute("aria-expanded", "false");
      fireEvent.click(tab);
      expect(tab).toHaveAttribute("aria-expanded", "true");
      expect(screen.getByText("Paper P")).toBeVisible();
    }));

  it("side-tab: empty state is a disabled tab", () =>
    withFlag("ui.page-sources", true, async () => {
      setVariant("page-sources", "side-tab");
      open(none);
      expect(await screen.findByRole("button", { name: "No sources" })).toBeDisabled();
    }));

  it("hover-marks: a count in the header opens a popover list on click", () =>
    withFlag("ui.page-sources", true, async () => {
      setVariant("page-sources", "hover-marks");
      open(some);
      const mark = await screen.findByRole("button", { name: "2 sources" });
      fireEvent.click(mark);
      const pop = await screen.findByRole("dialog", { name: "Sources" });
      expect(within(pop).getByText("Paper P")).toBeInTheDocument();
    }));

  it("flag off: no request and no sources UI", () =>
    withFlag("ui.page-sources", false, async () => {
      setVariant("page-sources", "footer");
      const calls: string[] = [];
      open(some, calls);
      await screen.findByText("Text.");
      expect(calls).toEqual([]);
      expect(screen.queryByRole("region", { name: "Page sources" })).toBeNull();
    }));
});
