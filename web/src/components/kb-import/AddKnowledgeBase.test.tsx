import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import type { KbImportPreview, KbInfo, KbList } from "@/api/types";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import type { ImportAdapter } from "./adapter";
import { AddKnowledgeBase } from "./AddKnowledgeBase";

const git = { repo: true, branch: "main" } as KbList["kbs"][number]["git"];
const list: KbList = { bases_dir: "/b", think_root: "/t", active: "alpha", kbs: [{ id: "alpha", name: "Alpha", root: "/b/alpha", schema_version: "1.3", error: "", active: true, git }] };
const info = { id: "alpha", name: "Alpha", root: "/b/alpha", git, bases_dir: "/b", relaunch: "x", types: [], digest: [], areas: [], source_fields: [], meta_overrides: [], flags_registry: "kb", schema_version: "1.3", config: null, think_root: "/t", think_git: git } as unknown as KbInfo;

const preview = (over: Partial<KbImportPreview> = {}): KbImportPreview => ({ id: "my-notes", name: "My notes", pages: 3, source: "my-notes.zip", errors: [], warnings: [], ref: "", commit: "", ok: true, ...over });
const zip = () => new File(["x"], "my-notes.zip", { type: "application/zip" });

/** The real app on System → Knowledge bases, with the import routes mocked at the data source (so the local adapter runs). */
async function system(over: Partial<DataSource> = {}, kind: DataSource["kind"] = "http") {
  const ds: DataSource = {
    ...mockDataSource({
      getKb: async () => info,
      listKbs: async () => list,
      getShareStatus: async () => ({ status: null, chip: null }),
      previewKbImport: vi.fn(async () => preview()),
      importKb: vi.fn(async (r) => ({ id: r.id ?? "my-notes", name: "My notes", root: "/b/my-notes", pages: 3 })),
      ...over,
    }),
    kind,
  };
  const router = createAppRouter(createMemoryHistory({ initialEntries: ["/system?tab=kbs"] }), "");
  render(<App source={ds} router={router} />);
  return { ds, router };
}

const addButton = () => screen.findByRole("button", { name: /Add knowledge base/ });
async function dropZip() {
  await userEvent.click(await addButton());
  await userEvent.upload(await screen.findByTestId("kb-zip-input"), zip());
}

describe("Add knowledge base dialog (System → Knowledge bases)", () => {
  it("a zip goes to a preview, Create imports it, and the result links to its graph", async () => {
    const { ds, router } = await system();
    await dropZip();
    expect(await screen.findByText("My notes")).toBeInTheDocument();
    expect(screen.getByText(/3 pages/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(ds.importKb).toHaveBeenCalledWith(expect.objectContaining({ id: "my-notes", file: expect.any(File) }));
    expect(await screen.findByText("Imported")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: "Open it" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/graph"));
    expect(router.state.location.search).toMatchObject({ kbs: "my-notes" });
  });

  it("errors disable Create, warnings are shown", async () => {
    await system({ previewKbImport: async () => preview({ ok: false, errors: ["a.md: [links] broken link"], warnings: ["b.md: no title"] }) });
    await dropZip();
    expect(await screen.findByText(/broken link/)).toBeInTheDocument();
    expect(screen.getByText(/no title/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  });

  it("warnings alone still allow Create", async () => {
    await system({ previewKbImport: async () => preview({ warnings: ["b.md: no title"] }) });
    await dropZip();
    await screen.findByText(/no title/);
    expect(screen.getByRole("button", { name: "Create" })).toBeEnabled();
  });

  it("editing the id validates it again before Create is allowed", async () => {
    const previewKbImport = vi.fn(async (r: { id?: string }) =>
      r.id === "taken" ? preview({ id: "taken", ok: false, errors: ["already exists"] }) : preview({ id: r.id ?? "my-notes" }));
    const { ds } = await system({ previewKbImport });
    await dropZip();
    const id = await screen.findByLabelText("Id");
    await userEvent.clear(id);
    await userEvent.type(id, "taken");
    expect(await screen.findByText("already exists")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
    await userEvent.clear(id);
    await userEvent.type(id, "fresh");
    await waitFor(() => expect(screen.getByRole("button", { name: "Create" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(ds.importKb).toHaveBeenCalledWith(expect.objectContaining({ id: "fresh" }));
  });

  it("a git URL is previewed through the same route", async () => {
    const { ds } = await system();
    await userEvent.click(await addButton());
    await userEvent.type(await screen.findByLabelText("From git URL"), "https://example.com/me/notes.git");
    await userEvent.click(screen.getByRole("button", { name: "Preview" }));
    await screen.findByText("My notes");
    expect(ds.previewKbImport).toHaveBeenCalledWith({ gitUrl: "https://example.com/me/notes.git", id: undefined });
  });

  it("a source the server cannot read stays on step 1 with its message", async () => {
    await system({ previewKbImport: async () => { throw new Error("not a readable zip"); } });
    await dropZip();
    expect(await screen.findByRole("alert")).toHaveTextContent("not a readable zip");
    expect(screen.queryByRole("button", { name: "Create" })).toBeNull();
  });

  it("a build without the local data source offers no import", async () => {
    await system({}, "embedded");
    await screen.findByText("Available knowledge bases");
    expect(screen.queryByRole("button", { name: /Add knowledge base/ })).toBeNull();
  });
});

describe("header menu entry (kb-view)", () => {
  it("has + Add knowledge base, which opens the same dialog", () =>
    withFlag("kb-view", true, async () => {
      await system();
      await userEvent.click(await screen.findByRole("button", { name: "Knowledge bases" }));
      const menu = await screen.findByRole("dialog", { name: "Knowledge bases on the graph" });
      await userEvent.click(within(menu).getByRole("button", { name: /Add knowledge base/ }));
      expect(await screen.findByRole("dialog", { name: "Add knowledge base" })).toBeInTheDocument();
    }));
});

describe("with another adapter", () => {
  it("a handed-over bundle shows the received card with the adapter's message and no link", async () => {
    const adapter: ImportAdapter = {
      validate: async () => ({ id: "x", name: "X", pages: 1, source: "x.zip", errors: [], warnings: [] }),
      submit: async () => ({ state: "received", message: "It appears after your Mac's next sync." }),
    };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <AddKnowledgeBase adapter={adapter} open onOpenChange={() => {}} />
      </QueryClientProvider>,
    );
    await userEvent.upload(await screen.findByTestId("kb-zip-input"), zip());
    await userEvent.click(await screen.findByRole("button", { name: "Create" }));
    expect(await screen.findByText("Received")).toBeInTheDocument();
    expect(screen.getByText(/next sync/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
