import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource, PageCard, PageDetail, PageIndex, Proposal } from "@/api";
import { proposalFixture, renderFixture, summaryFixture } from "@/features/proposals/fixtures";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";

const card = (id: string): PageCard => ({ id, title: `Title ${id}`, type: "idea", maturity: "", depth: "", areas: [], preview: "p", words: 10 });
const index: PageIndex = { generated_at: "t", pages: [card("tensor-rank"), card("matrix-rank")], links: [], wanted: [], wanted_total: 0 };
const detail: PageDetail = {
  card: card("tensor-rank"), path: "wiki/tensor-rank.md", frontmatter: {}, markdown: "# Tensor rank\n\nRank always determines the cost.\n",
  backlinks: [], outbound: [], broken: [], suggested: [],
};

function open(path: string, over: Partial<DataSource> = {}) {
  const ds: Partial<DataSource> = {
    listPages: async () => index,
    getPage: async () => detail,
    getPageSources: async () => ({ slug: "tensor-rank", sources: [], counts: { total: 0, raw: 0, pages: 0, external: 0, by_disposition: {} } }),
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
    getProposal: async () => proposalFixture(),
    getProposalRender: async () => renderFixture,
    listProposals: async () => [summaryFixture()],
    ...over,
  };
  render(<App source={mockDataSource(ds)} router={createAppRouter(createMemoryHistory({ initialEntries: [path] }), "")} />);
}

const on = (fn: () => Promise<void>) => withFlag("ui.proposals", true, () => withFlag("ui.page-review", true, fn));

describe("Page review (ui.page-review)", () => {
  beforeEach(() => localStorage.clear());

  it("flag off: ?review= is ignored and the page reads as usual", () =>
    withFlag("ui.proposals", true, () =>
      withFlag("ui.page-review", false, async () => {
        open("/pages/tensor-rank?review=p1");
        expect(await screen.findByRole("heading", { level: 1, name: "Title tensor-rank" })).toBeInTheDocument();
        expect(await screen.findByText("Rank always determines the cost.")).toBeInTheDocument();
        expect(screen.queryByTestId("review-line")).toBeNull();
        expect(screen.queryByTestId("review-card")).toBeNull();
        expect(screen.queryByTestId("waiting-line")).toBeNull();
      })));

  it("reading: an open proposal on the page shows as one line that opens its review", () =>
    on(async () => {
      open("/pages/tensor-rank");
      const line = await screen.findByTestId("waiting-line");
      expect(line).toHaveTextContent("1 proposal is waiting on this page");
      await userEvent.click(within(line).getByRole("link", { name: "Soften the rank claim" }));
      expect(await screen.findByTestId("review-line")).toHaveTextContent("Reviewing: Soften the rank claim");
    }));

  it("review: the page shows the edits in place and the card queues them with a tick and a cross", () =>
    on(async () => {
      const decided: unknown[] = [];
      const decideProposal = vi.fn(async (_id: string, body: { hunk_id: string; decision: string }) => {
        decided.push(body);
        return proposalFixture({ decisions: { [body.hunk_id]: { decision: body.decision } }, counts: { hunks: 3, accepted: 1, rejected: 0, corrected: 0 } } as unknown as Partial<Proposal>);
      });
      open("/pages/tensor-rank?review=p1", { decideProposal: decideProposal as never });
      expect(await screen.findByTestId("review-line")).toBeInTheDocument();
      // the whole page: the unchanged paragraph and the edit's new text, in place
      expect(await screen.findByText("An unchanged paragraph in between.")).toBeInTheDocument();
      expect(document.querySelector('[data-hunk="h-soften"]')).not.toBeNull();
      const cardEl = screen.getByTestId("review-card");
      expect(within(cardEl).getByRole("heading", { name: /Edits on this page/ })).toHaveTextContent("3");
      expect(within(cardEl).getAllByRole("listitem")).toHaveLength(3);
      const apply = within(cardEl).getByRole("button", { name: /^Apply 0 accepted changes$/ });
      expect(apply).toBeDisabled();
      await userEvent.click(within(cardEl).getByRole("button", { name: /^Accept: Rank often determines/ }));
      await waitFor(() => expect(decided).toEqual([{ hunk_id: "h-soften", decision: "accept" }]));
      expect(await within(cardEl).findByRole("button", { name: "Apply 1 accepted change" })).toBeEnabled();
      expect(within(cardEl).getByRole("button", { name: /^Accept: Rank often determines/ })).toHaveAttribute("aria-pressed", "true");
      // the neighbourhood graph gives way to the review card
      expect(screen.queryByRole("heading", { name: /Neighbourhood/ })).toBeNull();
    }));

  it("apply: sends the proposal and the way out leaves the review", () =>
    on(async () => {
      let applied = false;
      const accepted = { decisions: { "h-soften": { decision: "accept" } }, counts: { hunks: 3, accepted: 1, rejected: 0, corrected: 0 } } as unknown as Partial<Proposal>;
      const applyProposal = vi.fn(async () => {
        applied = true;
        return {} as never;
      });
      open("/pages/tensor-rank?review=p1", { getProposal: async () => proposalFixture(applied ? { ...accepted, status: "applied" } : accepted), applyProposal });
      await userEvent.click(await screen.findByRole("button", { name: "Apply 1 accepted change" }));
      await waitFor(() => expect(applyProposal).toHaveBeenCalledWith("p1"));
      const cardEl = await screen.findByTestId("review-card");
      await userEvent.click(await within(cardEl).findByRole("link", { name: "Back to the page" }));
      await waitFor(() => expect(screen.queryByTestId("review-line")).toBeNull());
    }));
});
