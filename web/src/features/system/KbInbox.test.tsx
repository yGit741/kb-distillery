import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { KbInbox, KbInboxItem, KbInfo, KbList } from "@/api/types";
import { mockDataSource } from "@/test/datasource";

const git = { repo: true, branch: "main" } as KbList["kbs"][number]["git"];
const list: KbList = { bases_dir: "/b", think_root: "/t", active: "alpha", kbs: [{ id: "alpha", name: "Alpha", root: "/b/alpha", schema_version: "1.3", error: "", active: true, git }] };
const info = { id: "alpha", name: "Alpha", root: "/b/alpha", git, bases_dir: "/b", relaunch: "x", types: [], digest: [], areas: [], source_fields: [], meta_overrides: [], flags_registry: "kb", schema_version: "1.3", config: null, think_root: "/t", think_git: git } as unknown as KbInfo;

const item = (over: Partial<KbInboxItem>): KbInboxItem => ({ item: "20260102T030405Z-aaaaaaaa", status: "pending", kind: "zip", at: "2026-01-02T03:04:05Z", uploader: "me@example.com", kb_id: "notes", pages: 3, warnings: 0, size: 10, ...over });

function system(over: Partial<DataSource> = {}) {
  const ds = mockDataSource({ getKb: async () => info, listKbs: async () => list, getShareStatus: async () => ({ status: null, chip: null }), ...over });
  render(<App source={ds} router={createAppRouter(createMemoryHistory({ initialEntries: ["/system?tab=kbs"] }), "")} />);
  return ds;
}
const inbox = (items: KbInboxItem[]): KbInbox => ({ configured: true, items, error: "", guide: "" });

describe("System → Knowledge bases → Inbox", () => {
  it("lists pending, imported and failed uploads", async () => {
    system({
      getKbInbox: async () => inbox([
        item({}),
        item({ item: "20260101T030405Z-bbbbbbbb", status: "imported", kind: "git", git_url: "https://example.com/old.git", kb_id: "old" }),
        item({ item: "20251231T030405Z-cccccccc", status: "failed", kb_id: "bad", error: "id taken" }),
      ]),
    });
    const table = await screen.findByTestId("inbox-table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(within(rows[0]!).getByText("pending")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("3 pages")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("imported")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("https://example.com/old.git")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("failed")).toBeInTheDocument();
    expect(within(rows[2]!).getByText("id taken")).toBeInTheDocument();
  });

  it("not set up is a one-line hint with the guide link, not an error, and no Pull button", async () => {
    system({ getKbInbox: async () => ({ configured: false, items: [], error: "", guide: "https://example.com/import-a-bundle.md" }) });
    const hint = await screen.findByText(/Site uploads are not set up on this Mac/);
    expect(within(hint).getByRole("link", { name: "How to set them up" })).toHaveAttribute("href", expect.stringContaining("import-a-bundle.md"));
    expect(screen.queryByRole("button", { name: /Pull now/ })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("an unreachable site is shown inline", async () => {
    system({ getKbInbox: async () => ({ configured: true, items: [], error: "cannot reach https://x", guide: "" }) });
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot reach https://x");
  });

  it("Pull now imports the pending uploads and shows the result in the same card as the dialog", async () => {
    const pull = vi.fn(async () => ({ imported: [{ item: "i", kb_id: "notes", error: "" }], failed: [{ item: "j", kb_id: "", error: "boom" }], unreported: [] }));
    const getKbInbox = vi.fn(async () => inbox([item({})]));
    system({ getKbInbox, pullKbInbox: pull });
    await userEvent.click(await screen.findByRole("button", { name: /Pull now/ }));
    expect(pull).toHaveBeenCalledOnce();
    const card = (await screen.findByText("Imported 1")).closest('[role="status"]')!;
    expect(card).toHaveTextContent("notes");
    expect(card).toHaveTextContent("j: boom");
    await vi.waitFor(() => expect(getKbInbox).toHaveBeenCalledTimes(2));          // the list is read again
  });

  it("Pull now is off when nothing is pending", async () => {
    system({ getKbInbox: async () => inbox([item({ status: "imported" })]) });
    expect(await screen.findByRole("button", { name: /Pull now/ })).toBeDisabled();
  });
});
