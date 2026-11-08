import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { ApiError, DataSourceProvider, type DataSource } from "@/api";
import type { DigestJob, DigestPreview } from "@/api/types";
import { FirstRunCard } from "@/features/first-run/FirstRunCard";
import { snapshot } from "@/features/pipeline/fixtures";
import { PipelineView } from "@/features/pipeline/PipelineView";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";

const opt = (backend: string, over: Record<string, unknown> = {}) => ({
  backend, available: true, why: "", tokens_in: 20000, tokens_out: 4000, cost_usd: 0.4, cost_worst_usd: 0.8, billed_usd: backend === "subscription" ? 0 : 0.4,
  seconds: 120, eta: "about 2 min", ...over,
});

const preview: DigestPreview = {
  tier: "full", depth: "full", provider: "anthropic", model: "claude-sonnet", backend: "subscription", backend_why: "You are signed in, so it runs on your subscription.",
  tokens_in: 20000, tokens_out: 4000, cost_usd: 0.4, cost_worst_usd: 0.8, billed_usd: 0, seconds: 120, eta: "about 2 min", requests: 2, sources: 2, skipped: [],
  options: [opt("subscription"), opt("api"), opt("batch", { eta: "up to 24 hours", cost_usd: 0.2, billed_usd: 0.2, cost_worst_usd: 0.4 })],
};

const job = (over: Partial<DigestJob> = {}): DigestJob => ({
  id: "j1", status: "running", backend: "subscription", backend_why: "", created: "2026-11-08T10:00:00Z", current: "raw/web-clips/queued.md", depth: "full", model: "m", provider: "anthropic",
  spent_usd: 0, tier: "full",
  sources: [
    { raw: "raw/printed-docs/2022-listed.pdf", status: "finalized", note: "", page: "wiki/paper-listed.md", seconds: 30 },
    { raw: "raw/web-clips/queued.md", status: "digesting", note: "", page: null, seconds: null },
  ],
  ...over,
});

async function mount(ui: ReactNode, over: Partial<DataSource> = {}) {
  const root = createRootRoute();
  const index = createRoute({ getParentRoute: () => root, path: "/", component: () => (
    <DataSourceProvider source={mockDataSource({ getPipeline: async () => snapshot, listDigestJobs: async () => ({ jobs: [] }), ...over })}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>
    </DataSourceProvider>
  ) });
  const router = createRouter({ routeTree: root.addChildren([index]), history: createMemoryHistory({ initialEntries: ["/"] }) });
  render(<RouterProvider router={router} />);
  await waitFor(() => expect(document.body.textContent).not.toBe(""));
}

const pipeline = () => <PipelineView search={{}} onSearch={() => {}} />;
const firstRun = () => <FirstRunCard host={{ go: () => {}, href: () => "/" }} />;

describe("digest jobs flag", () => {
  it("is absent on the pipeline when screen.digest-jobs is off", () =>
    withFlag("screen.digest-jobs", false, async () => {
      await mount(pipeline());
      await screen.findByText("Add sources");
      expect(screen.queryByTestId("digest-jobs")).not.toBeInTheDocument();
    }));

  it("is absent on the first-run card when off", () =>
    withFlag("screen.digest-jobs", false, async () => {
      await mount(firstRun());
      expect(screen.queryByTestId("digest-jobs")).not.toBeInTheDocument();
    }));

  it("shows on the first-run card when on", () =>
    withFlag("screen.digest-jobs", true, async () => {
      await mount(firstRun());
      expect(await screen.findByTestId("digest-jobs")).toBeInTheDocument();
    }));
});

describe("digest jobs (flag on)", () => {
  it("previews, lets the backend be picked per run, and starts the job with that backend", () =>
    withFlag("screen.digest-jobs", true, async () => {
      const previewDigest = vi.fn(async () => preview);
      const startDigestJob = vi.fn(async () => job({ status: "queued" }));
      await mount(pipeline(), { previewDigest, startDigestJob });
      const list = await screen.findByRole("list", { name: "Sources to digest" });
      await userEvent.click(within(list).getByLabelText(/2022-listed\.pdf/));
      await userEvent.click(screen.getByRole("button", { name: /Preview digest \(1\)/ }));
      expect(previewDigest).toHaveBeenCalledWith(["raw/printed-docs/2022-listed.pdf"]);
      const sub = await screen.findByLabelText(/Subscription/);
      expect(sub).toBeChecked();
      expect(screen.getByText("Included in your subscription")).toBeInTheDocument();
      expect(screen.getByText("up to 24 hours")).toBeInTheDocument();
      await userEvent.click(screen.getByLabelText(/Batch/));
      await userEvent.click(screen.getByRole("button", { name: "Start on Batch" }));
      await waitFor(() => expect(startDigestJob).toHaveBeenCalledWith(["raw/printed-docs/2022-listed.pdf"], "batch"));
    }));

  it("disables a backend that is not available and says why", () =>
    withFlag("screen.digest-jobs", true, async () => {
      const p = { ...preview, options: [opt("subscription", { available: false, why: "Not signed in to Claude." }), opt("api"), opt("batch")], backend: "api" };
      await mount(pipeline(), { previewDigest: async () => p });
      await userEvent.click(within(await screen.findByRole("list", { name: "Sources to digest" })).getByLabelText(/queued\.md/));
      await userEvent.click(screen.getByRole("button", { name: /Preview digest/ }));
      expect(await screen.findByLabelText(/Subscription/)).toBeDisabled();
      expect(screen.getByText("Not signed in to Claude.")).toBeInTheDocument();
      expect(screen.getByLabelText(/^API/)).toBeChecked();
    }));

  it("shows a refusal plainly", () =>
    withFlag("screen.digest-jobs", true, async () => {
      await mount(pipeline(), { previewDigest: async () => { throw new ApiError("Another digest job is already running.", 409); } });
      await userEvent.click(within(await screen.findByRole("list", { name: "Sources to digest" })).getByLabelText(/queued\.md/));
      await userEvent.click(screen.getByRole("button", { name: /Preview digest/ }));
      expect(await screen.findByTestId("digest-refusal")).toHaveTextContent("Another digest job is already running.");
      expect(screen.getByRole("button", { name: /^Start/ })).toBeDisabled();
    }));

  it("lists a running job with progress and cancels it", () =>
    withFlag("screen.digest-jobs", true, async () => {
      const cancelDigestJob = vi.fn(async () => job({ status: "cancelled" }));
      await mount(pipeline(), { listDigestJobs: async () => ({ jobs: [job()] }), cancelDigestJob });
      const row = await screen.findByTestId("digest-job");
      expect(within(row).getByText("Running")).toBeInTheDocument();
      expect(within(row).getByText("1 of 2")).toBeInTheDocument();
      expect(within(row).getByText("Now: queued.md")).toBeInTheDocument();
      await userEvent.click(within(row).getByRole("button", { name: /Cancel/ }));
      await waitFor(() => expect(cancelDigestJob).toHaveBeenCalledWith("j1"));
    }));

  it("a finished job links to the pages it wrote and has no cancel", () =>
    withFlag("screen.digest-jobs", true, async () => {
      const done = job({ status: "finished", current: null, spent_usd: 0.31, backend: "api" });
      await mount(pipeline(), { listDigestJobs: async () => ({ jobs: [done] }) });
      const row = await screen.findByTestId("digest-job");
      await userEvent.click(within(row).getByRole("button", { name: "Show sources" }));
      expect(within(row).getByRole("link", { name: "paper-listed" })).toHaveAttribute("href", "/pages/paper-listed");
      expect(within(row).queryByRole("button", { name: /Cancel/ })).not.toBeInTheDocument();
      expect(within(row).getByText("$0.31 spent")).toBeInTheDocument();
    }));

  it("shows a failed job's reason", () =>
    withFlag("screen.digest-jobs", true, async () => {
      await mount(pipeline(), { listDigestJobs: async () => ({ jobs: [job({ status: "failed", error: "The worker stopped.", current: null })] }) });
      expect(await screen.findByRole("alert")).toHaveTextContent("The worker stopped.");
    }));
});
