import { setTestFlagOverrides } from "@/flags";
import { createMemoryHistory } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { RelationProposals } from "@/api/types";
import { mockDataSource } from "@/test/datasource";
import { groupBySubject, rangeToSearch, readRange } from "./logic";
import { sampleSnapshot } from "@/features/graph/fixtures";
import { useGraphUi } from "@/features/graph/store";

// The old path now redirects into the graph's sheet; jsdom has no canvas, so force-graph is a chainable no-op.
vi.mock("force-graph", () => {
  const make = () => {
    const proxy: unknown = new Proxy({}, { get: (_t, name: string) => (name === "_destructor" ? () => {} : () => proxy) });
    return proxy;
  };
  return { default: () => () => make() };
});
beforeEach(() => useGraphUi.setState({ flyout: null }));


const row = (from: string, to: string, kind: string, confidence: number, extra = {}) => ({
  from, from_title: from.toUpperCase(), to, to_title: to.toUpperCase(), kind, confidence,
  note: "", evidence: "", status: confidence < 0.5 ? "low-confidence" : "proposed", run: "r1", ...extra,
});
const ALL = [row("a", "b", "uses", 0.95, { note: "a relies on b" }), row("a", "c", "extends", 0.7), row("d", "a", "uses", 0.35)];

function setup(over: Partial<DataSource> = {}, url = "/app/relations") {
  const calls: { min: number; max: number; kind?: string }[] = [];
  const ds = mockDataSource({
    getGraph: async () => sampleSnapshot(),
    getRelationProposals: async (o) => {
      calls.push(o);
      const rows = ALL.filter((r) => r.confidence >= o.min && r.confidence <= o.max && (!o.kind || r.kind === o.kind));
      return { rows, total: ALL.length, shown: rows.length, kinds: ["extends", "uses"], histogram: [0, 0, 0, 1, 0, 0, 0, 1, 0, 1] } as unknown as RelationProposals;
    },
    getShareStatus: async () => ({ status: null, chip: null }),
    ...over,
  });
  const router = createAppRouter(createMemoryHistory({ initialEntries: [url] }));
  render(<App source={ds} router={router} />);
  return { ds, router, calls };
}

describe("range helpers", () => {
  it("reads, orders and clamps the percent range", () => {
    expect(readRange(undefined, undefined)).toEqual({ min: 0, max: 100 });
    expect(readRange("90", "100")).toEqual({ min: 90, max: 100 });
    expect(readRange("80", "20")).toEqual({ min: 20, max: 80 });
    expect(readRange("-5", "250")).toEqual({ min: 0, max: 100 });
    expect(readRange("x", "")).toEqual({ min: 0, max: 100 });
  });
  it("leaves the URL empty for the full range", () => {
    expect(rangeToSearch({ min: 0, max: 100 })).toEqual({});
    expect(rangeToSearch({ min: 90, max: 100 })).toEqual({ min: "90" });
    expect(rangeToSearch({ min: 0, max: 50 })).toEqual({ max: "50" });
  });
  it("groups rows by subject keeping the order", () => {
    const g = groupBySubject(ALL as never);
    expect(g.map((x) => [x.slug, x.rows.length])).toEqual([["a", 2], ["d", 1]]);
  });
});

describe("RelationsScreen", () => {
  // these screens are not about the calm default; the folded graph behind them opens on the old Map
  beforeEach(() => {
    setTestFlagOverrides({ "calm-graph": false });
    useGraphUi.setState({ story: "map" });
  });

  it("shows everything by default, grouped, with the count", async () => {
    setup();
    expect(await screen.findByText(/Showing 3 of 3/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "A" })[0]).toHaveAttribute("href", expect.stringContaining("/pages/a"));
    expect(screen.getByText("a relies on b")).toBeInTheDocument();
    expect(screen.getByText("below the 50% cut")).toBeInTheDocument();
  });

  it("restores the range from the URL and asks the API for exactly that range", async () => {
    const { calls } = setup({}, "/app/relations?min=90&max=100");
    expect(await screen.findByText(/Showing 1 of 3 between 90% and 100%/)).toBeInTheDocument();
    expect(calls.at(-1)).toEqual({ min: 0.9, max: 1, kind: undefined });
    expect(screen.queryByText("a relies on b")).toBeInTheDocument();
    expect(screen.queryByText("C")).not.toBeInTheDocument();
  });

  it("a preset button and the sliders change the range", async () => {
    const { calls } = setup();
    await screen.findByText(/Showing 3 of 3/);
    await userEvent.click(screen.getByRole("button", { name: "0–50" }));
    expect(await screen.findByText(/Showing 1 of 3 between 0% and 50%/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/From/), { target: { value: "30" } });
    await waitFor(() => expect(calls.at(-1)).toEqual({ min: 0.3, max: 0.5, kind: undefined }));
  });

  it("the kind selector narrows the list", async () => {
    const { calls } = setup();
    await screen.findByText(/Showing 3 of 3/);
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "extends");
    await waitFor(() => expect(calls.at(-1)?.kind).toBe("extends"));
  });

  it("says so when the range holds nothing", async () => {
    setup({}, "/app/relations?min=5&max=10");
    expect(await screen.findByText(/No proposals in this range/)).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    setup({ getRelationProposals: async () => { throw new Error("boom"); } });
    expect(await screen.findByText("Could not load the proposals", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
