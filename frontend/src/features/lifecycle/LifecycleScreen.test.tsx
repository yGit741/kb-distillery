import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type DataSource, type LifecycleSnapshot, type TimelineRow } from "@/api";
import { LifecycleScreen } from "./LifecycleScreen";

const row = (o: Partial<TimelineRow>): TimelineRow => ({
  sha: "a".repeat(40), short: "aaaaaaaaa", date: "2026-10-23T10:00:00+00:00", subject: "", kind: "kb", type: null,
  scope: null, summary: null, kb_version: null, pr: null, retro: false, parents: [], op: null, target: null,
  reverts: null, reverted_by: null, snapshot_tag: null, ...o,
});

const snap: LifecycleSnapshot = {
  generated_at: "2026-10-24T08:00:00Z", branch: "main", head: "d2ebc69", version: "0.13.1", next_version: "0.13.2",
  github: "https://github.com/o/r", schema: { version: "0.13", applied: ["0001"], pending: [] },
  policy: { hooks_installed: true, mode: "enforce", strict: false },
  timeline: [
    row({ sha: "1".repeat(40), short: "111111111", subject: "kb(refine): unlabeled leftovers (kb-0.13.1)", kb_version: "0.13.1", op: "refine", target: "x" }),
    row({ sha: "2".repeat(40), short: "222222222", subject: "chore(git): run CI on a runner (#60)", kind: "pr-merge", type: "chore", pr: 60 }),
  ],
  snapshots: [{ tag: "kb-0.13.0", date: "2026-10-23", label: "baseline" }],
  stats: { kb_steps: 1, pr_merges: 1, ops_30d: {}, undone: 0 },
  working: { lanes: { knowledge: 0, tooling: 2 }, knowledge: [], tooling: [], think_dirty: 0,
    sessions: { ingest: [], distill: [], researcher: [], ops: null }, unpushed: 0 },
  infra_branches: [{ name: "infra/frontend-shell", date: "2026-10-24", last: "feat", ahead: 1, behind: 0 }],
  nightly: { plist_installed: true, log: "~/log", summary: "ok", hint: null },
  stale_worktrees: [],
};

function renderWith(getLifecycle: DataSource["getLifecycle"]) {
  const ds: DataSource = {
    kind: "http", getLifecycle,
    getShareStatus: async () => ({ status: null, chip: null }),
    getGraphNodes: async () => [],
  };
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <LifecycleScreen />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

describe("LifecycleScreen", () => {
  it("shows a loading state, then summary, history, snapshots and branches", async () => {
    renderWith(async () => snap);
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(await screen.findByText("kb-0.13.1", { selector: "div" })).toBeInTheDocument();
    expect(screen.getByText(/run CI on a runner/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /#60/ })).toHaveAttribute("href", "https://github.com/o/r/pull/60");
    expect(screen.getByText("baseline")).toBeInTheDocument();
    expect(screen.getByText("infra/frontend-shell")).toBeInTheDocument();
  });

  it("filters history by kind and search", async () => {
    renderWith(async () => snap);
    await screen.findByTestId("timeline");
    await userEvent.click(screen.getByRole("tab", { name: "Infra PRs" }));
    const list = screen.getByTestId("timeline");
    expect(within(list).queryByText(/unlabeled leftovers/)).toBeNull();
    expect(within(list).getByText(/run CI/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search history"), "zzz");
    expect(screen.getByText("No commits match.")).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    renderWith(async () => { throw new Error("boom"); });
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("handles an empty history and a shared snapshot without working state", async () => {
    const { working: _w, infra_branches: _b, nightly: _n, stale_worktrees: _s, ...shared } = snap;
    renderWith(async () => ({ ...shared, timeline: [], snapshots: [] }));
    expect(await screen.findByText("No history yet.")).toBeInTheDocument();
    expect(screen.getByText(/No snapshots yet/)).toBeInTheDocument();
    expect(screen.getByText(/not part of this snapshot/)).toBeInTheDocument();
    expect(screen.queryByText("Open infra branches")).toBeNull();
  });
});
