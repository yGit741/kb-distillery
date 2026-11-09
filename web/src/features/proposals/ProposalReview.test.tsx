import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createHttpDataSource, DataSourceProvider, type DataSource, type Proposal } from "@/api";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { setVariant } from "@/components/variants";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { proposalFixture, renderFixture } from "./fixtures";
import { applyBlocker, reviewOrder, segments } from "./model";
import ProposalsScreen from "./index";

function setup(over: Partial<DataSource> = {}, p: Proposal = proposalFixture()) {
  const decideProposal = vi.fn(async (_id: string, d: { hunk_id: string; decision: string; comment?: string }) =>
    proposalFixture({ decisions: { [d.hunk_id]: { decision: d.decision as "accept", comment: d.comment ?? "", suggested: false } }, counts: { hunks: 3, accepted: d.decision === "accept" ? 1 : 0, rejected: 0, corrected: 0 } }),
  );
  const ds = mockDataSource({ getProposal: async () => p, getProposalRender: async () => renderFixture, decideProposal, ...over });
  const root = createRootRoute();
  const list = createRoute({ getParentRoute: () => root, path: "/proposals", component: ProposalsScreen });
  const one = createRoute({ getParentRoute: () => root, path: "/proposals/$id", component: ProposalsScreen });
  const router = createRouter({ routeTree: root.addChildren([list, one]), history: createMemoryHistory({ initialEntries: ["/proposals/p1"] }) });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { decideProposal };
}

afterEach(() => {
  try {
    localStorage.clear();
  } catch {
    /* no storage */
  }
  act(() => setVariant("proposal-diff", "inline"));
});

describe("proposal model", () => {
  it("keeps a paragraph edit that adds a link in the page text, frontmatter in the strip", () => {
    const p = proposalFixture();
    const segs = segments(renderFixture.pages[0], p.hunks);
    expect(segs.map((s) => (s.kind === "hunk" ? s.hunk.id : `same:${s.blocks.map((b) => b.index).join(",")}`))).toEqual(["same:1", "h-soften", "same:3", "h-link"]);
    expect(reviewOrder(p.hunks, renderFixture.pages).map((h) => h.id)).toEqual(["h-fm", "h-soften", "h-link"]);
  });
});

describe("proposal review screen", () => {
  it.each(["inline", "side-by-side", "reading"])("renders the %s view with every hunk and the Structure strip", async (view) => {
    act(() => setVariant("proposal-diff", view));
    setup();
    expect(await screen.findByRole("heading", { name: "Soften the rank claim" })).toBeInTheDocument();
    expect(screen.getByText("Structure · 1 change")).toBeInTheDocument();
    expect(screen.getByText("Set maturity")).toBeInTheDocument();
    await waitFor(() => expect(document.querySelector('[data-hunk="h-soften"]')).not.toBeNull());
    expect(document.querySelector('[data-hunk="h-link"]')).not.toBeNull();
    expect(screen.getByRole("radio", { name: view.replace(/-/g, " ") })).toHaveAttribute("aria-checked", "true");
    if (view === "inline") {
      expect(screen.getByText("always").tagName).toBe("DEL");
      expect(screen.getByText("often").tagName).toBe("INS");
      expect(screen.getAllByTestId("why-line")[0]).toHaveTextContent("why: the claim is too strong · from: paper-x");
    }
    if (view === "side-by-side") expect(screen.getAllByText("1 unchanged paragraph")).toHaveLength(2);
    if (view === "reading") {
      expect(screen.queryByText("always")).not.toBeInTheDocument();
      await userEvent.click(screen.getAllByRole("button", { name: /changed: show what changed/ })[0]!);
      expect(within(screen.getByTestId("margin-note")).getByText("always")).toBeInTheDocument();
    }
  });

  it("switches the view from the header control", async () => {
    setup();
    await screen.findByRole("heading", { name: "Soften the rank claim" });
    await userEvent.click(screen.getByRole("radio", { name: "side by side" }));
    expect(await screen.findByText("Before")).toBeInTheDocument();
  });

  it("posts accept, and correct with the comment", async () => {
    const { decideProposal } = setup();
    await screen.findByRole("heading", { name: "Soften the rank claim" });
    const block = document.querySelector('[data-hunk="h-soften"]') as HTMLElement;
    await userEvent.click(within(block).getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(decideProposal).toHaveBeenCalledWith("p1", { hunk_id: "h-soften", decision: "accept" }));
    expect(await within(document.querySelector('[data-hunk="h-soften"]') as HTMLElement).findByText("Accepted")).toBeInTheDocument();

    const link = document.querySelector('[data-hunk="h-link"]') as HTMLElement;
    await userEvent.click(within(link).getByRole("button", { name: "Correct" }));
    await userEvent.type(screen.getByRole("textbox", { name: "What should change?" }), "cite the survey too");
    await userEvent.click(screen.getByRole("button", { name: "Save note" }));
    await waitFor(() => expect(decideProposal).toHaveBeenLastCalledWith("p1", { hunk_id: "h-link", decision: "correct", comment: "cite the survey too" }));
  });

  it("walks hunks with j/k and acts with a / r / c", async () => {
    const { decideProposal } = setup();
    await screen.findByRole("heading", { name: "Soften the rank claim" });
    await waitFor(() => expect(document.querySelector('[data-hunk="h-soften"]')).not.toBeNull());
    await userEvent.keyboard("j");
    expect(document.querySelector('[data-hunk="h-fm"]')).toHaveAttribute("data-focused", "true");
    await userEvent.keyboard("j");
    expect(document.querySelector('[data-hunk="h-soften"]')).toHaveAttribute("data-focused", "true");
    await userEvent.keyboard("r");
    await waitFor(() => expect(decideProposal).toHaveBeenCalledWith("p1", { hunk_id: "h-soften", decision: "reject" }));
    await userEvent.keyboard("k");
    expect(document.querySelector('[data-hunk="h-fm"]')).toHaveAttribute("data-focused", "true");
    await userEvent.keyboard("c"); // a structure line has no Correct
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    await userEvent.keyboard("jj");
    expect(document.querySelector('[data-hunk="h-link"]')).toHaveAttribute("data-focused", "true");
    await userEvent.keyboard("c");
    expect(screen.getByRole("textbox", { name: "What should change?" })).toHaveFocus();
    await userEvent.keyboard("a"); // typing in the box is not a shortcut
    expect(decideProposal).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/next \/ previous change/)).toBeInTheDocument();
  });

  it("keeps Apply off with the reason while an error finding targets a hunk that is not rejected", async () => {
    const blocked = proposalFixture({
      checks: { tier1: [{ severity: "error", code: "link", message: "link to a missing page", slug: "tensor-rank", hunk_id: "h-link", source: "tier1" }], tier2: [] },
      decisions: { "h-soften": { decision: "accept", comment: "", suggested: false }, "h-link": { decision: "accept", comment: "", suggested: false } },
      counts: { hunks: 3, accepted: 2, rejected: 0, corrected: 0 },
    });
    expect(applyBlocker(blocked, blocked.checks.tier1, blocked.hunks)).toMatch(/reject it to apply the rest/);
    setup({}, blocked);
    const apply = await screen.findByRole("button", { name: "Apply accepted (2)" });
    expect(apply).toBeDisabled();
    expect(screen.getByTestId("apply-reason")).toHaveTextContent("A check fails on the change");
    await userEvent.click(screen.getByRole("button", { name: "1 error" }));
    expect(screen.getByRole("dialog", { name: "Check findings" })).toHaveTextContent("link to a missing page");

    const ok = proposalFixture({ decisions: { "h-soften": { decision: "accept", comment: "", suggested: false } }, counts: { hunks: 3, accepted: 1, rejected: 0, corrected: 0 } });
    expect(applyBlocker(ok, [...ok.checks.tier1], ok.hunks)).toBeNull();
  });

  it("shows a calm stale banner and keeps Apply off", async () => {
    setup({}, proposalFixture({ stale: true, status: "stale", counts: { hunks: 3, accepted: 1, rejected: 0, corrected: 0 } }));
    expect(await screen.findByTestId("stale-banner")).toHaveTextContent("The page changed since this proposal was made");
    expect(screen.getByRole("button", { name: "Apply accepted (1)" })).toBeDisabled();
  });

  it("lists proposals at /proposals", async () => {
    const ds = mockDataSource({
      listProposals: async () => [{ id: "p1", title: "Soften the rank claim", status: "open", producer: { kind: "chat" }, created: "2026-11-08T20:00:00+00:00", updated: "", pages: ["tensor-rank"], counts: { hunks: 3, accepted: 1, rejected: 0, corrected: 0 }, checks: { errors: 0, warnings: 1, blocking: 0 } }],
    });
    const root = createRootRoute();
    const list = createRoute({ getParentRoute: () => root, path: "/proposals", component: ProposalsScreen });
    const router = createRouter({ routeTree: root.addChildren([list]), history: createMemoryHistory({ initialEntries: ["/proposals"] }) });
    render(
      <DataSourceProvider source={ds}>
        <QueryClientProvider client={new QueryClient()}>
          <RouterProvider router={router} />
        </QueryClientProvider>
      </DataSourceProvider>,
    );
    expect(await screen.findByRole("link", { name: "Soften the rank claim" })).toHaveAttribute("href", "/proposals/p1");
    expect(screen.getByText("3 changes · 1 accepted")).toBeInTheDocument();
  });
});

describe("decision wiring", () => {
  it("sends {hunk_id, decision, comment} to POST /api/proposals/{id}/decisions", async () => {
    const calls: { url: string; method: string; body: unknown }[] = [];
    const fetchImpl = async (req: Request | string | URL, init?: RequestInit) => {
      const r = req instanceof Request ? req : new Request(String(req), init);
      calls.push({ url: r.url, method: r.method, body: await r.clone().json().catch(() => null) });
      return new Response(JSON.stringify(proposalFixture()), { status: 200, headers: { "Content-Type": "application/json" } });
    };
    const ds = createHttpDataSource(fetchImpl as typeof fetch, "http://localhost");
    await ds.decideProposal("p1", { hunk_id: "h-link", decision: "correct", comment: "cite it" });
    expect(calls).toEqual([{ url: "http://localhost/api/proposals/p1/decisions", method: "POST", body: { hunk_id: "h-link", decision: "correct", comment: "cite it" } }]);
  });
});

describe("route /proposals/$id (ui.proposals)", () => {
  const ds = () =>
    mockDataSource({
      getLifecycle: () => new Promise(() => {}),
      getOps: () => new Promise(() => {}),
      getHealth: () => new Promise(() => {}),
      getShareStatus: async () => ({ status: null, chip: null }),
      getGraphNodes: async () => [],
      getProposal: async () => proposalFixture(),
      getProposalRender: async () => renderFixture,
    });
  beforeEach(() => void vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null));
  afterEach(() => vi.restoreAllMocks());

  it("is Not Found while the flag is off", () =>
    withFlag("ui.proposals", false, async () => {
      render(<App source={ds()} router={createAppRouter(createMemoryHistory({ initialEntries: ["/proposals/p1"] }), "")} />);
      expect(await screen.findByText("Not Found")).toBeInTheDocument();
    }));

  it("shows the review while the flag is on", () =>
    withFlag("ui.proposals", true, async () => {
      render(<App source={ds()} router={createAppRouter(createMemoryHistory({ initialEntries: ["/proposals/p1"] }), "")} />);
      expect(await screen.findByRole("heading", { name: "Soften the rank claim" })).toBeInTheDocument();
    }));
});
