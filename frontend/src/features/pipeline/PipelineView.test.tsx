import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { vi } from "vitest";
import { DataSourceProvider, type DataSource } from "@/api";
import type { PipelineSearch } from "@/routes/search";
import { mockDataSource } from "@/test/datasource";
import { snapshot } from "./fixtures";
import { PipelineView, type SearchPatch } from "./PipelineView";

function Harness({ initial = {} }: { initial?: PipelineSearch }) {
  const [s, setS] = useState(initial);
  return <PipelineView search={s} onSearch={(p: SearchPatch) => setS((prev: PipelineSearch) => Object.fromEntries(Object.entries({ ...prev, ...p }).filter(([, v]) => v !== undefined)) as PipelineSearch)} />;
}

async function mount(ds: DataSource, initial: PipelineSearch = {}) {
  const root = createRootRoute();
  const index = createRoute({ getParentRoute: () => root, path: "/", component: () => (
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Harness initial={initial} />
      </QueryClientProvider>
    </DataSourceProvider>
  ) });
  const router = createRouter({ routeTree: root.addChildren([index]), history: createMemoryHistory({ initialEntries: ["/"] }) });
  render(<RouterProvider router={router} />);
  await waitFor(() => expect(document.body.textContent).not.toBe(""));
}

describe("PipelineView", () => {
  it("shows a loading state, then the three steps with counts", async () => {
    await mount(mockDataSource({ getPipeline: async () => snapshot }));
    expect(await screen.findByRole("heading", { name: "Pipeline" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Add" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Catalog" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Digest" })).toBeInTheDocument();
    expect(screen.getByText(/6 items · 3 in the backlog/)).toBeInTheDocument();
    expect(screen.queryByText(/hub|catalog depth/i)).toBeNull();
  });

  it("shows an error with retry", async () => {
    const getPipeline = vi.fn().mockRejectedValueOnce(new Error("boom")).mockResolvedValue(snapshot);
    await mount(mockDataSource({ getPipeline }));
    expect(await screen.findByText("Could not load the pipeline")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { name: "Pipeline" })).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    await mount(mockDataSource({ getPipeline: async () => ({ ...snapshot, items: [] }) }));
    expect(await screen.findByText(/raw layer is empty/i)).toBeInTheDocument();
  });

  it("filters by depth through the step buttons and by text, and switches view", async () => {
    await mount(mockDataSource({ getPipeline: async () => snapshot }));
    await screen.findByRole("heading", { name: "Pipeline" });
    expect(screen.getByRole("button", { name: "Preview 2021-deep.pdf" })).toBeInTheDocument();
    await userEvent.click(within(screen.getByRole("region", { name: "Digest" })).getByRole("button", { name: /deep/ }));
    expect(screen.queryByRole("button", { name: "Preview 2020-easy.pdf" })).toBeNull();
    expect(screen.getByRole("button", { name: "Preview 2021-deep.pdf" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await userEvent.type(screen.getByLabelText("Search"), "queued");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Preview 2020-easy.pdf" })).toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "board" }));
    expect(screen.getByRole("region", { name: "not digested" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "timeline" }));
    expect(screen.getByText(/Newest first/)).toBeInTheDocument();
  });

  it("honours URL filters and backlog", async () => {
    await mount(mockDataSource({ getPipeline: async () => snapshot }), { backlog: "queued", format: "web-clips" });
    await screen.findByRole("heading", { name: "Pipeline" });
    expect(screen.getByRole("button", { name: "Preview queued.md" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview 2020-easy.pdf" })).toBeNull();
    expect(screen.getByRole("button", { name: "Backlog only" })).toHaveAttribute("aria-pressed", "true");
  });

  it("lists failures in the ingestion status log", async () => {
    await mount(mockDataSource({ getPipeline: async () => snapshot }));
    await screen.findByRole("heading", { name: "Pipeline" });
    expect(screen.getByText("arXiv did not answer")).toBeInTheDocument();
  });

  it("previews text, asks before digesting, and shows the result (mock only)", async () => {
    const digestRaw = vi.fn().mockResolvedValue({ command: "kb easy-digest raw/web-clips/queued.md", exit: 0, stdout: "written", stderr: "" });
    const getRawPreview = vi.fn().mockResolvedValue({ path: "raw/web-clips/queued.md", exists: true, ext: "md", file_url: "", format: "web-clips", text: "# Hello clip", collection: [] });
    await mount(mockDataSource({ getPipeline: async () => snapshot, digestRaw, getRawPreview }), { item: "raw/web-clips/queued.md" });
    expect(await screen.findByRole("heading", { name: "Hello clip" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Easy digest/ }));
    expect(digestRaw).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Run easy digest" }));
    expect(await screen.findByText("written")).toBeInTheDocument();
    expect(digestRaw).toHaveBeenCalledExactlyOnceWith("raw/web-clips/queued.md");
  });

  it("shows a digest error and allows cancelling", async () => {
    const digestRaw = vi.fn().mockRejectedValue(new Error("not a digestible file"));
    const getRawPreview = vi.fn().mockResolvedValue({ path: "p", exists: true, ext: "md", file_url: "", format: "x", text: "x", collection: [] });
    await mount(mockDataSource({ getPipeline: async () => snapshot, digestRaw, getRawPreview }), { item: "raw/web-clips/queued.md" });
    await userEvent.click(await screen.findByRole("button", { name: /Easy digest/ }));
    await userEvent.click(screen.getByRole("button", { name: "Run easy digest" }));
    expect(await screen.findByText("not a digestible file")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: /Easy digest/ })).toBeInTheDocument();
  });

  it("uses the typed thumbnail endpoint for a PDF", async () => {
    await mount(mockDataSource({ getPipeline: async () => snapshot }), { item: "raw/printed-docs/2020-easy.pdf" });
    const img = await screen.findByRole("img", { name: /First page of 2020-easy.pdf/ });
    expect(img.getAttribute("src")).toBe("/api/raw/raw/printed-docs/2020-easy.pdf/thumb?w=900");
  });
});
