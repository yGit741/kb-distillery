import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource, type Proposal } from "@/api";
import { setVariant } from "@/components/variants";
import { mockDataSource } from "@/test/datasource";
import { feedItems, inboxFixture, inboxRows, proposalFixture, renderFixture } from "./fixtures";
import ProposalsScreen from "./index";

function setup(over: Partial<DataSource> = {}, path = "/proposals") {
  const getProposalInbox = vi.fn(async (o?: { status?: string; group?: string }) => inboxFixture(inboxRows, o?.group));
  const ds = mockDataSource({ getProposalInbox, getProposalFeed: async () => ({ feed: feedItems }), ...over });
  const root = createRootRoute();
  const list = createRoute({ getParentRoute: () => root, path: "/proposals", component: ProposalsScreen });
  const one = createRoute({ getParentRoute: () => root, path: "/proposals/$id", component: ProposalsScreen });
  const router = createRouter({ routeTree: root.addChildren([list, one]), history: createMemoryHistory({ initialEntries: [path] }) });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { getProposalInbox };
}

afterEach(() => {
  try {
    localStorage.clear();
  } catch {
    /* no storage */
  }
  act(() => setVariant("proposal-inbox", "by-page"));
});

const headings = () => screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);

describe("review inbox layouts", () => {
  it("by-page: one section per page, a proposal on two pages under each", async () => {
    const { getProposalInbox } = setup();
    expect(await screen.findAllByRole("link", { name: "Fix twenty link targets" })).toHaveLength(2);
    expect(getProposalInbox).toHaveBeenCalledWith({ status: "open", group: "page" });
    expect(headings()).toEqual(["matrix-rank", "survey", "tensor-rank"]);
  });

  it("by-class: claims first, links after, with a class chip count", async () => {
    act(() => setVariant("proposal-inbox", "by-class"));
    const { getProposalInbox } = setup();
    await screen.findByRole("link", { name: "Soften the rank claim" });
    expect(getProposalInbox).toHaveBeenCalledWith({ status: "open", group: "class" });
    expect(headings()).toEqual(["Claims", "New pages", "Links"]);
    const row = screen.getByRole("link", { name: "Fix twenty link targets" }).closest("li")!;
    expect(within(row).getByText("20 links")).toBeInTheDocument();
    expect(within(row).getByTestId("tier-mark")).toHaveTextContent("auto-apply");
  });

  it("timeline: a flat list in the order given, no sections", async () => {
    act(() => setVariant("proposal-inbox", "timeline"));
    const { getProposalInbox } = setup();
    await screen.findByRole("link", { name: "Soften the rank claim" });
    expect(getProposalInbox).toHaveBeenCalledWith({ status: "open" });
    expect(screen.queryAllByRole("heading", { level: 2 })).toHaveLength(0);
    expect(screen.getAllByTestId("proposal-row").map((r) => r.getAttribute("data-id"))).toEqual(["p1", "p2", "p3", "p4"]);
  });

  it("the filter bar asks for the chosen status", async () => {
    const { getProposalInbox } = setup();
    await screen.findByRole("link", { name: "Soften the rank claim" });
    await userEvent.click(screen.getByRole("radio", { name: "Applied" }));
    await waitFor(() => expect(getProposalInbox).toHaveBeenLastCalledWith({ status: "applied", group: "page" }));
  });

  it("a stale proposal shows the badge and Rebase calls the endpoint", async () => {
    const rebaseProposal = vi.fn(async (id: string) => ({ proposal: proposalFixture({ id }), dropped: [] }));
    act(() => setVariant("proposal-inbox", "timeline"));
    setup({ rebaseProposal });
    const row = (await screen.findByRole("link", { name: "Retarget a link" })).closest("li")!;
    expect(within(row).getByTestId("stale-badge")).toHaveTextContent("page changed since");
    await userEvent.click(within(row).getByRole("button", { name: "Rebase" }));
    await waitFor(() => expect(rebaseProposal).toHaveBeenCalledWith("p4"));
    expect(screen.getAllByRole("button", { name: "Rebase" })).toHaveLength(1);
  });
});

describe("feed", () => {
  it("lists applied and undone, Undo calls the endpoint, a blocked one says why", async () => {
    const undoProposal = vi.fn(async (id: string) => proposalFixture({ id, status: "undone" }));
    setup({ undoProposal });
    await userEvent.click(await screen.findByRole("tab", { name: /Feed/ }));
    const rows = await screen.findAllByTestId("feed-row");
    expect(rows).toHaveLength(3);
    const [fresh, blocked, undone] = rows as [HTMLElement, HTMLElement, HTMLElement];
    expect(within(fresh).getByText("auto-applied")).toBeInTheDocument();
    await userEvent.click(within(fresh).getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(undoProposal).toHaveBeenCalledWith("f1"));
    expect(within(blocked).getByRole("button", { name: "Undo" })).toBeDisabled();
    expect(within(blocked).getByTestId("undo-reason")).toHaveTextContent("Later changes touched matrix-rank");
    expect(within(undone).queryByRole("button", { name: "Undo" })).toBeNull();
    expect(within(undone).getByText("undone")).toBeInTheDocument();
  });
});

describe("review of a multi-page proposal", () => {
  const multi = (over: Partial<Proposal> = {}): Proposal => {
    const base = proposalFixture();
    const other = { ...base.hunks[0]!, id: "h-other", slug: "matrix-rank", at: 1 };
    const hunks = [...base.hunks, other];
    return proposalFixture({ hunks, base: { "tensor-rank": "a", "matrix-rank": "b" }, counts: { hunks: 4, accepted: 0, rejected: 0, corrected: 0 }, revisions: [{ ...base.revisions[0]!, hunks }], ...over });
  };

  it("switches pages with tabs", async () => {
    setup({ getProposal: async () => multi(), getProposalRender: async () => renderFixture }, "/proposals/p1");
    await screen.findByRole("heading", { name: "Soften the rank claim" });
    await userEvent.click(screen.getByRole("tab", { name: /matrix-rank/ }));
    await waitFor(() => expect(document.querySelector('[data-hunk="h-other"]')).not.toBeNull());
    expect(document.querySelector('[data-hunk="h-soften"]')).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: /All pages/ }));
    await waitFor(() => expect(document.querySelector('[data-hunk="h-soften"]')).not.toBeNull());
  });

  it("the stale notice rebases, and the dropped changes are listed calmly", async () => {
    let state: Proposal = multi({ stale: true, status: "stale", stale_pages: ["tensor-rank"] });
    const dropped = { hunk_id: "h-gone", slug: "tensor-rank", klass: "claims", op: "edit_page", before: "Old.\n", after: "New claim text.\n", reason: "the text it changed is no longer on the page" };
    const rebaseProposal = vi.fn(async () => {
      state = multi({ revisions: [{ ...multi().revisions[0]!, dropped: [dropped] }] });
      return { proposal: state, dropped: [dropped] };
    });
    setup({ getProposal: async () => state, getProposalRender: async () => renderFixture, rebaseProposal }, "/proposals/p1");
    const banner = await screen.findByTestId("stale-banner");
    expect(banner).toHaveTextContent("tensor-rank");
    await userEvent.click(within(banner).getByRole("button", { name: "Rebase" }));
    await waitFor(() => expect(rebaseProposal).toHaveBeenCalledWith("p1"));
    const list = await screen.findByTestId("dropped-list");
    expect(list).toHaveTextContent("1 change could not be carried over");
    expect(list).toHaveTextContent("New claim text.");
    expect(screen.queryByTestId("stale-banner")).toBeNull();
  });
});

