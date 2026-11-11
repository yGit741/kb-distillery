import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource, type Proposal } from "@/api";
import { proposalFixture, renderFixture } from "@/features/proposals/fixtures";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { EditPreviewHost } from "./Host";
import { planOf } from "./Plan";
import { useEditPreview } from "./store";

const card = (id: string, title: string) => ({ id, title, type: "idea", maturity: "", depth: "", areas: [], preview: "", words: 1 });
const index = { generated_at: "t", pages: [card("tensor-rank", "Tensor rank")], links: [], wanted: [], wanted_total: 0 };

function setup(over: Partial<DataSource> = {}, preview?: string) {
  const ds = mockDataSource({
    getProposal: async () => proposalFixture(),
    getProposalRender: async () => renderFixture,
    listPages: (async () => index) as never,
    ...over,
  });
  const root = createRootRoute();
  const graph = createRoute({ getParentRoute: () => root, path: "/graph", component: () => <EditPreviewHost preview={preview} /> });
  const page = createRoute({ getParentRoute: () => root, path: "/pages/$slug", component: () => <p>page view</p> });
  const router = createRouter({ routeTree: root.addChildren([graph, page]), history: createMemoryHistory({ initialEntries: ["/graph"] }) });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return router;
}

const on = (fn: () => Promise<void>) => withFlag("ui.edit-preview", true, () => withFlag("ui.ingest", true, fn));

describe("edit preview plan", () => {
  beforeEach(() => act(() => useEditPreview.getState().reset()));

  it("planOf: new pages, updated pages, links, and what is safe to accept unread", () => {
    const p = proposalFixture();
    const plan = planOf(p, (s) => s === "tensor-rank", () => undefined);
    expect([plan.newPages, plan.updated, plan.links]).toEqual([0, 1, 1]);
    // the link edit and the front matter insert are safe; the reworded claim needs a look
    expect(plan.safe.map((h) => h.id).sort()).toEqual(["h-fm", "h-link"]);
    expect(plan.look.map((h) => h.id)).toEqual(["h-soften"]);
    expect(planOf(p, () => false, () => undefined).look).toEqual([]);
  });

  it("a proposal link opens its plan: counts, the graph, the pages, and Apply held back", () =>
    on(async () => {
      setup({}, "p1");
      const sheet = await screen.findByTestId("plan-sheet");
      expect(await within(sheet).findByTestId("plan-line")).toHaveTextContent("0 new pages · 1 page updated · 1 new link");
      expect(within(sheet).getByRole("group", { name: "Pages this touches" })).toBeInTheDocument();
      expect(within(within(sheet).getByRole("list", { name: "Pages in this plan" })).getByRole("listitem")).toHaveTextContent(/Tensor rank.*3 changes.*3 open/);
      expect(within(sheet).getByRole("button", { name: "Apply 0 accepted changes" })).toBeDisabled();
      expect(within(sheet).getByText(/1 change rewrite or remove text/)).toBeInTheDocument();
    }));

  it("accepts the safe changes in one go and leaves the rewrite for the page", () =>
    on(async () => {
      const sent: string[] = [];
      const decideProposal = vi.fn(async (_id: string, body: { hunk_id: string; decision: string }) => {
        sent.push(body.hunk_id);
        return proposalFixture({ decisions: Object.fromEntries(sent.map((h) => [h, { decision: "accept" }])), counts: { hunks: 3, accepted: sent.length, rejected: 0, corrected: 0 } } as unknown as Partial<Proposal>);
      });
      const router = setup({ decideProposal: decideProposal as never, getProposal: async () => proposalFixture(sent.length ? ({ decisions: Object.fromEntries(sent.map((h) => [h, { decision: "accept" }])), counts: { hunks: 3, accepted: sent.length, rejected: 0, corrected: 0 } } as unknown as Partial<Proposal>) : {}) }, "p1");
      await userEvent.click(await screen.findByRole("button", { name: "Accept the 2 safe changes" }));
      await waitFor(() => expect(sent.sort()).toEqual(["h-fm", "h-link"]));
      expect(await screen.findByRole("button", { name: "Apply 2 accepted changes" })).toBeEnabled();
      // a page opens in the Page Explorer's review mode, and the pop-up closes
      await userEvent.click(screen.getByRole("button", { name: "Tensor rank" }));
      expect(await screen.findByText("page view")).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/pages/tensor-rank");
      expect(router.state.location.search).toEqual({ review: "p1" });
      expect(screen.queryByTestId("plan-sheet")).toBeNull();
    }));

  it("a dropped file is read deep, shows its step, then the plan of its proposal", () =>
    on(async () => {
      const startIngest = vi.fn(async () => ({ job_id: "j1" }));
      let done = false;
      const job = () => ({ id: "j1", status: done ? "done" : "running", source: "paper.pdf", tier: "deep", collection: "", kind: "file", backend: "", started: 0, finished: null, step: "digest", error: null, pages: [], proposal_id: done ? "p1" : null, steps: [{ name: "digest", state: "active", detail: "page 3 of 9" }] });
      setup({ startIngest: startIngest as never, getIngestJob: (async () => job()) as never, ingestEvents: (async () => new Response(null, { status: 500 })) as never });
      await screen.findByText(() => true, undefined, { timeout: 50 }).catch(() => undefined);
      fireEvent.drop(window, { dataTransfer: { types: ["Files"], files: [new File(["x"], "paper.pdf", { type: "application/pdf" })] } });
      const sheet = await screen.findByTestId("plan-sheet");
      await waitFor(() => expect(startIngest).toHaveBeenCalledWith(expect.objectContaining({ tier: "deep" })));
      expect(await within(sheet).findByText(/Reading the source: digest · page 3 of 9/)).toBeInTheDocument();
      done = true;
      expect(await within(sheet).findByTestId("plan-line", undefined, { timeout: 4000 })).toBeInTheDocument();
    }));

  it("a file that cannot be ingested says why and starts nothing", () =>
    on(async () => {
      const startIngest = vi.fn();
      setup({ startIngest: startIngest as never });
      await act(async () => {});
      fireEvent.drop(window, { dataTransfer: { types: ["Files"], files: [new File(["x"], "photo.png", { type: "image/png" })] } });
      expect(await screen.findByRole("alert")).toHaveTextContent(/cannot be ingested here/);
      expect(startIngest).not.toHaveBeenCalled();
    }));
});
