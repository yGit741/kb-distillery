import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { ScopeDetail } from "@/api/types";
import { useKb } from "@/lib/store";
import { mockDataSource } from "@/test/datasource";
import { DRAFTS_KEY } from "./logic";

const rows: ScopeDetail["rows"] = [
  { path: "raw/printed-docs/2020-a.pdf", format: "printed-docs", disposition: "digested", slug: "paper-a", digestion: "full", collection: ["course-rl"], page_type: "paper", year: 2020 },
  { path: "raw/handwritten/b.pdf", format: "handwritten", disposition: "queued", slug: null, digestion: "", collection: [], page_type: null, year: null },
];
const detail: ScopeDetail = {
  slug: "scope-one", title: "Scope one", why: "because", status: "active", rows,
  projection: { hop0: ["x"], hop1: [], covered: [], uncovered: ["y"], hubs: [], themes: [], coverage: 0.5 },
};
const summary = { slug: "scope-one", title: "Scope one", status: "active", files: 2, digested: 1, uncovered: 1, coverage: 0.5, updated: "2026-10-23T10:00:00" };

function setup(over: Partial<DataSource> = {}, url = "/app/scopes") {
  const ds = mockDataSource({
    listScopes: async () => ({ scopes: [summary] }),
    getScope: async () => detail,
    getShareStatus: async () => ({ status: null, chip: null }),
    ...over,
  });
  const router = createAppRouter(createMemoryHistory({ initialEntries: [url] }));
  render(<App source={ds} router={router} />);
  return { ds, router };
}

describe("ScopesScreen", () => {
  beforeEach(() => {
    localStorage.clear();
    useKb.setState({ selection: new Set(), scopeDraftId: null });
  });

  it("lists scopes and opens one with stats, projection and rows", async () => {
    setup();
    await userEvent.click(await screen.findByRole("button", { name: /Scope one/ }));
    expect(await screen.findByTestId("stats")).toHaveTextContent("2 files · 1 digested · 50%");
    expect(screen.getByTestId("projection")).toHaveTextContent("1 pages cite these files");
    expect(screen.getByText("2020-a.pdf")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open in graph" })).toHaveAttribute("href", expect.stringContaining("scope=scope-one"));
    expect(screen.getByRole("link", { name: "Ask in chat" })).toHaveAttribute("href", expect.stringContaining("/chat"));
  });

  it("shows empty and error states", async () => {
    setup({ listScopes: async () => ({ scopes: [] }) });
    expect(await screen.findByText("No scopes yet.")).toBeInTheDocument();
  });

  it("shows an error with retry", async () => {
    setup({ listScopes: async () => { throw new Error("boom"); } });
    expect(await screen.findByText("Could not load scopes", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("removes rows, saves the remaining paths and confirms delete in-app", async () => {
    const saveScope = vi.fn(async () => ({ ok: true, slug: "scope-one", sha: "abcdef123456", version: "kb-1.0.1" }));
    const deleteScope = vi.fn(async () => ({ ok: true, slug: "scope-one" }));
    setup({ saveScope, deleteScope }, "/app/scopes?scope=scope-one");
    await userEvent.click(await screen.findByRole("button", { name: "Remove b.pdf" }));
    expect(screen.getByText("unsaved changes")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saveScope).toHaveBeenCalledWith({ slug: "scope-one", title: "Scope one", why: "because", paths: ["raw/printed-docs/2020-a.pdf"], create: false }));
    expect(await screen.findByText(/Saved as kb-1\.0\.1/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dlg = await screen.findByRole("dialog");
    expect(deleteScope).not.toHaveBeenCalled();
    await userEvent.click(within(dlg).getByRole("button", { name: "Delete scope" }));
    await waitFor(() => expect(deleteScope).toHaveBeenCalledWith("scope-one"));
  });

  it("duplicates through a dialog", async () => {
    const duplicateScope = vi.fn(async () => ({ ok: true, slug: "scope-one-copy" }));
    setup({ duplicateScope }, "/app/scopes?scope=scope-one");
    await userEvent.click(await screen.findByRole("button", { name: "Duplicate" }));
    const dlg = await screen.findByRole("dialog");
    await userEvent.click(within(dlg).getByRole("button", { name: "Duplicate" }));
    await waitFor(() => expect(duplicateScope).toHaveBeenCalledWith("scope-one", { new_slug: "scope-one-copy", title: "Scope one (copy)" }));
  });

  it("opens a graph draft, validates, then creates", async () => {
    localStorage.setItem(DRAFTS_KEY, JSON.stringify({ active: "scope-d", drafts: { "scope-d": { slug: "scope-d", title: "From graph", isNew: true, rows: [rows[0]] } } }));
    const saveScope = vi.fn(async () => ({ ok: true, slug: "scope-d" }));
    setup({ saveScope }, "/app/scopes?draft=scope-d");
    expect(await screen.findByDisplayValue("From graph")).toBeInTheDocument();
    expect(useKb.getState().scopeDraftId).toBe("scope-d");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText(/Why is required/)).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: /Why/ }), "to study");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(saveScope).toHaveBeenCalledWith({ slug: "scope-d", title: "From graph", why: "to study", paths: [rows[0]?.path], create: true }));
    await waitFor(() => expect(localStorage.getItem(DRAFTS_KEY)).not.toContain("From graph"));
  });

  it("searches raw files and previews a resolve before adding", async () => {
    const resolveScope = vi.fn(async (_b: { nodes: string[] }) => ({ paths: ["raw/printed-docs/2021-c.pdf"], rows: [{ ...(rows[1] as ScopeDetail["rows"][number]), path: "raw/printed-docs/2021-c.pdf", format: "printed-docs" }] }));
    setup({
      resolveScope,
      listPages: async () => ({ generated_at: "", links: [], wanted: [], pages: [{ id: "idea-c", title: "Gamma idea", type: "idea", areas: [], depth: "", preview: "", status: "", words: 1 }] }) as never,
      getCorpus: async (f) => ({ columns: [], count: 1, format: f ?? "", rows: f === "emails" ? [{ path: "raw/emails/2020-t/thread.md", collection: [], digestion: "", sha1: "", title: "", disposition: "queued" }] : [] }) as never,
    }, "/app/scopes?scope=scope-one");
    await userEvent.type(await screen.findByLabelText("Search pages and raw files"), "gamma");
    await userEvent.click(await screen.findByRole("button", { name: "Resolve" }));
    const prev = await screen.findByRole("region", { name: "Resolve preview" });
    expect(await within(prev).findByText(/1 raw file, 1 not in the scope yet/)).toBeInTheDocument();
    await userEvent.click(within(prev).getByRole("button", { name: "Add 1 file" }));
    expect(await screen.findByText("2021-c.pdf")).toBeInTheDocument();
    expect(resolveScope).toHaveBeenCalledWith({ nodes: ["idea-c"] });

    await userEvent.clear(screen.getByLabelText("Search pages and raw files"));
    await userEvent.type(screen.getByLabelText("Search pages and raw files"), "thread");
    await userEvent.click(await screen.findByRole("button", { name: "Add 2020-t/thread.md" }));
    expect(await screen.findByText("2020-t/thread.md")).toBeInTheDocument();
  });
});
