import { createMemoryHistory } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { PageCard, PageCompare, PageDetail, PageHistory, PageIndex } from "@/api/types";
import { resetEmbed } from "@/app/embed";
import { setVariant } from "@/components/variants";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";

const card = (id: string): PageCard => ({ id, title: `Title ${id}`, type: "idea", maturity: "", depth: "", areas: [], preview: "p", words: 10 });
const index: PageIndex = { generated_at: "t", pages: [card("claim")], links: [], wanted: [], wanted_total: 0 };
const detail: PageDetail = {
  card: card("claim"), path: "wiki/claim.md", frontmatter: {}, markdown: "# Title claim\n\nRank is strong.\n",
  backlinks: [], outbound: [], broken: [], suggested: [],
};
const history: PageHistory = {
  slug: "claim",
  versions: [
    { sha: "c".repeat(40), short: "ccccccc", date: "2026-11-05T10:00:00+00:00", subject: "kb(refine): soften claim (kb-1.0.2)", kind: "refine" },
    { sha: "b".repeat(40), short: "bbbbbbb", date: "2026-10-20T10:00:00+00:00", subject: "kb(digest): add evidence (kb-1.0.1)", kind: "digest" },
    { sha: "a".repeat(40), short: "aaaaaaa", date: "2026-10-01T10:00:00+00:00", subject: "chore: first", kind: "other" },
  ],
};
const compare = (from: string, to: string): PageCompare =>
  ({
    from, to,
    hunks: [{
      id: "h1", op_id: "history", op: "edit_page", slug: "claim", kind: "prose", klass: "claims", at: 1, span: 1,
      before: "Rank is very strong.\n", after: "Rank is strong.\n",
      tokens: [["equal", "Rank is "], ["delete", "very "], ["equal", "strong.\n"]],
      reason: "", sources: [], links_added: [], links_removed: [],
    }],
    page: {
      slug: "claim", exists: true, text: "", my_notes: "", hunks: [],
      blocks: [{ index: 0, kind: "heading", text: "# Title claim\n\n" }, { index: 1, kind: "prose", text: "Rank is very strong.\n" }],
    },
  }) as unknown as PageCompare;

function open(over: Partial<DataSource> = {}) {
  const ds: Partial<DataSource> = {
    listPages: async () => index,
    getPage: async () => detail,
    getPageSources: async () => ({ slug: "claim", sources: [], counts: { total: 0, raw: 0, pages: 0, external: 0, by_disposition: {} } }),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
    getPageHistory: async () => history,
    ...over,
  };
  render(<App source={mockDataSource(ds)} router={createAppRouter(createMemoryHistory({ initialEntries: ["/pages/claim"] }), "")} />);
}

describe("Page history (ui.page-history)", () => {
  beforeEach(() => {
    localStorage.clear();
    resetEmbed();
  });
  afterEach(() => {
    act(() => {
      setVariant("page-history-entry", "header");
      setVariant("proposal-diff", "inline");
    });
  });

  it("header: the clock opens a panel listing the versions newest first with kind and subject", () =>
    withFlag("ui.page-history", true, async () => {
      setVariant("page-history-entry", "header");
      open();
      await userEvent.click(await screen.findByRole("button", { name: /History/ }));
      const panel = await screen.findByRole("complementary", { name: "Page history" });
      const rows = await within(panel).findAllByRole("checkbox");
      expect(rows).toHaveLength(3);
      expect(rows[0]).toHaveTextContent("2026-11-05");
      expect(rows[0]).toHaveTextContent("refine");
      expect(rows[0]).toHaveTextContent("soften claim");
      expect(rows[2]).toHaveTextContent("2026-10-01");
    }));

  it("header: one version against now calls compare with that sha and working, then renders the diff", () =>
    withFlag("ui.page-history", true, async () => {
      setVariant("page-history-entry", "header");
      const comparePage = vi.fn(async (_s: string, f: string, t?: string) => compare(f, t ?? "working"));
      open({ comparePage });
      await userEvent.click(await screen.findByRole("button", { name: /History/ }));
      const panel = await screen.findByRole("complementary", { name: "Page history" });
      await userEvent.click((await within(panel).findAllByRole("checkbox"))[1]!);
      await userEvent.click(within(panel).getByRole("button", { name: "Compare" }));
      await waitFor(() => expect(comparePage).toHaveBeenCalledWith("claim", "b".repeat(40), "working"));
      await waitFor(() => expect(document.querySelector('[data-hunk="h1"]')).not.toBeNull());
      // history only shows: nothing here restores or edits
      expect(screen.queryByRole("button", { name: /Restore/ })).toBeNull();
    }));

  it("timeline: two dots compare the older with the newer, whatever the click order", () =>
    withFlag("ui.page-history", true, async () => {
      setVariant("page-history-entry", "timeline");
      const comparePage = vi.fn(async (_s: string, f: string, t?: string) => compare(f, t ?? "working"));
      open({ comparePage });
      const strip = await screen.findByRole("navigation", { name: "Page history timeline" });
      const dots = await within(strip).findAllByRole("button", { name: /kb\(|chore/ });
      expect(dots).toHaveLength(3);
      expect(screen.queryByRole("button", { name: /^History/ })).toBeNull();
      await userEvent.click(dots[2]!); // newest
      await userEvent.click(dots[0]!); // oldest
      await userEvent.click(within(strip).getByRole("button", { name: "Compare" }));
      await waitFor(() => expect(comparePage).toHaveBeenCalledWith("claim", "a".repeat(40), "c".repeat(40)));
    }));

  it("off: no history entry at all", () =>
    withFlag("ui.page-history", false, async () => {
      const getPageHistory = vi.fn(async () => history);
      open({ getPageHistory });
      await screen.findByRole("heading", { name: /Title claim/ });
      expect(screen.queryByRole("button", { name: /History/ })).toBeNull();
      expect(screen.queryByRole("navigation", { name: "Page history timeline" })).toBeNull();
      expect(getPageHistory).not.toHaveBeenCalled();
    }));
});
