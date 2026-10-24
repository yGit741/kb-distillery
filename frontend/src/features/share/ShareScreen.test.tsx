import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type LifecycleSnapshot, type TimelineRow } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { AdminError, type AdminClient, type SnapshotList } from "./adminApi";
import { ShareScreen } from "./ShareScreen";

const snap = (name: string, o: Partial<SnapshotList["snapshots"][number]> = {}) => ({
  worker: `snapshot-20261020-${name}`, name, url: `https://snapshot-20261020-${name}.example.workers.dev/`,
  kb_version: "1.0.1", content_sha: "abcdef1234", built_at: "2026-10-20T10:00:00Z", views_7d: 7, online: true as const, behind_main: 2, ...o,
});
const list: SnapshotList = { snapshots: [snap("cohen"), snap("dead", { online: false, behind_main: null })], main: { kb_version: "1.0.3" }, notes: ["views: analytics unavailable"] };
const kb = (v: string): TimelineRow => ({ sha: v, short: v, date: "2026-10-23T10:00:00+00:00", subject: `kb(refine): ${v}`, kind: "kb", kb_version: v, summary: `step ${v}` }) as TimelineRow;

function client(over: Partial<AdminClient> = {}): AdminClient {
  return {
    listSnapshots: async () => list,
    prunePlan: async () => ({ dry_run: true, orphans: ["snapshot-20261020-dead"], unknown: [], foreign: ["other"], ok: [] }),
    deleteSnapshot: async (w) => ({ deleted: w, url: "" }),
    ...over,
  };
}

function renderIt(c: AdminClient) {
  const ds = mockDataSource({ getLifecycle: async () => ({ timeline: [kb("1.0.3"), kb("1.0.2")] }) as unknown as LifecycleSnapshot });
  return render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ShareScreen client={c} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

describe("ShareScreen", () => {
  it("loads, then lists snapshots with main version, notes and the prune plan", async () => {
    renderIt(client());
    expect(screen.getByRole("status", { name: /loading/i })).toBeInTheDocument();
    expect(await screen.findByText("cohen", { selector: "div" })).toBeInTheDocument();
    expect(screen.getByText("2 behind")).toBeInTheDocument();
    expect(screen.getByText("down")).toBeInTheDocument();
    expect(screen.getByTestId("main-version")).toHaveTextContent("main is kb-1.0.3");
    expect(screen.getByText(/analytics unavailable/)).toBeInTheDocument();
    expect(await screen.findByTestId("prune-plan")).toHaveTextContent("snapshot-20261020-dead");
  });

  it("shows the empty state", async () => {
    renderIt(client({ listSnapshots: async () => ({ snapshots: [], main: { kb_version: null }, notes: [] }), prunePlan: async () => ({ dry_run: true, orphans: [], unknown: [], foreign: [], ok: [] }) }));
    expect(await screen.findByText("No snapshots yet.")).toBeInTheDocument();
    expect(await screen.findByTestId("prune-clean")).toBeInTheDocument();
  });

  it("explains a missing token with the setup command, and a signed-out session", async () => {
    const { unmount } = renderIt(client({ listSnapshots: async () => { throw new AdminError(503, "panel not configured: set CF_API_TOKEN"); } }));
    expect(await screen.findByText(/panel not configured/)).toBeInTheDocument();
    expect(screen.getByText(/secret put CF_API_TOKEN/)).toBeInTheDocument();
    unmount();
    renderIt(client({ listSnapshots: async () => { throw new AdminError(401, "sign in first"); } }));
    expect(await screen.findByText(/Signed out/)).toBeInTheDocument();
  });

  it("builds the create command from the version picker and name; update fills it in replace mode", async () => {
    const u = userEvent.setup();
    renderIt(client());
    await screen.findByText("cohen", { selector: "div" });
    const cmd = await screen.findByTestId("snapshot-command");
    await waitFor(() => expect(cmd).toHaveTextContent("<name> kb-1.0.3"));
    await u.selectOptions(await screen.findByLabelText("Knowledge version"), "kb-1.0.2");
    await u.type(screen.getByLabelText("Snapshot name"), "new-one");
    expect(cmd).toHaveTextContent("pixi run share -- snapshot new-one kb-1.0.2");
    await u.clear(screen.getByLabelText("Snapshot name"));
    await u.type(screen.getByLabelText("Snapshot name"), "cohen");
    expect(screen.getByText(/name exists/)).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Copy" }).at(-1)).toBeDisabled();
    const row = screen.getByText("cohen", { selector: "div" }).closest("tr")!;
    await u.click(within(row).getByRole("button", { name: "Update" }));
    expect(screen.getByLabelText("Snapshot name")).toHaveValue("cohen");
    expect(cmd).toHaveTextContent("--replace");
  });

  it("deletes only after the name is typed, then reloads", async () => {
    const u = userEvent.setup();
    const del = vi.fn(async (w: string) => ({ deleted: w, url: "" }));
    renderIt(client({ deleteSnapshot: del }));
    await u.click(await screen.findByRole("button", { name: "Delete cohen" }));
    const go = screen.getByRole("button", { name: "Delete" });
    expect(go).toBeDisabled();
    await u.type(screen.getByLabelText("Type the snapshot name"), "snapshot-20261020-cohen");
    await u.click(go);
    await waitFor(() => expect(del).toHaveBeenCalledWith("snapshot-20261020-cohen", "snapshot-20261020-cohen"));
    expect(await screen.findByText("Deleted snapshot-20261020-cohen.")).toBeInTheDocument();
  });

  it("keeps the dialog open with the server's message when delete fails", async () => {
    const u = userEvent.setup();
    renderIt(client({ deleteSnapshot: async () => { throw new AdminError(502, "Cloudflare failed — may still be live"); } }));
    await u.click(await screen.findByRole("button", { name: "Delete cohen" }));
    await u.type(screen.getByLabelText("Type the snapshot name"), "snapshot-20261020-cohen");
    await u.click(screen.getByRole("button", { name: "Delete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("may still be live");
  });

  it("offers the history and rollback commands for a chosen snapshot", async () => {
    const u = userEvent.setup();
    renderIt(client());
    await screen.findByText("cohen", { selector: "div" });
    await u.click(screen.getByText("History and rollback (CLI)"));
    expect(screen.getByText("pixi run share -- history cohen")).toBeInTheDocument();
    await u.selectOptions(screen.getByLabelText("Snapshot for the CLI commands"), "dead");
    expect(screen.getByText("pixi run share -- rollback --worker snapshot-20261020-dead")).toBeInTheDocument();
  });
});
