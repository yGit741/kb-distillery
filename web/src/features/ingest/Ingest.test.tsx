import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { DataSourceProvider, type DataSource } from "@/api";
import type { IngestInput, IngestJob } from "@/api/types";
import { setVariant } from "@/components/variants";
import { mockDataSource } from "@/test/datasource";
import IngestScreen from "./index";

const STEPS = ["fetch", "convert", "digest", "propose"];
const job = (states: string[], over: Partial<IngestJob> = {}): IngestJob => ({
  id: "j1", status: "running", source: "notes.md", tier: "full", collection: "", pages: [], proposal_id: null, error: null,
  steps: STEPS.map((name, i) => ({ name, state: states[i] ?? "pending", detail: name === "convert" && states[1] === "done" ? "raw/web-clips/notes.md" : "" })),
  ...over,
});

const enc = new TextEncoder();
/** An SSE Response that delivers the given frames one chunk at a time. */
function sse(frames: [string, unknown][]): Response {
  let i = 0;
  const body = new ReadableStream<Uint8Array>({
    pull(c) {
      if (i >= frames.length) return c.close();
      const [event, data] = frames[i++]!;
      c.enqueue(enc.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

function setup(over: Partial<DataSource> = {}) {
  const startIngest = vi.fn(async (_input: IngestInput) => ({ job_id: "j1" }));
  const ds = mockDataSource({
    startIngest,
    listPages: async () => ({ pages: [{ id: "series-rl", type: "series" }, { id: "alpha", type: "idea" }] }) as never,
    ingestEvents: async () => sse([["job", job(["skipped", "active"])], ["job", job(["skipped", "done", "active"])], ["job", job(["skipped", "done", "done", "done"], { status: "done", proposal_id: "p9", pages: ["article-notes", "tensor-rank"] })], ["end", { status: "done" }]]),
    ...over,
  });
  const root = createRootRoute();
  const route = createRoute({ getParentRoute: () => root, path: "/ingest", component: IngestScreen });
  const router = createRouter({ routeTree: root.addChildren([route]), history: createMemoryHistory({ initialEntries: ["/ingest"] }) });
  render(
    <DataSourceProvider source={ds}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
  return { startIngest };
}

afterEach(() => {
  try {
    localStorage.clear();
  } catch {
    /* no storage */
  }
  act(() => setVariant("ingest-layout", "single"));
});

const note = () => new File(["# Notes\n\ntext"], "notes.md", { type: "text/markdown" });

describe("single layout", () => {
  it("sends the dropped file with the default tier, then shows the job and the proposal link", async () => {
    const { startIngest } = setup();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Choose a file"), note());
    expect(await screen.findByText("notes.md")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(startIngest).toHaveBeenCalledTimes(1));
    const arg = startIngest.mock.calls[0]![0];
    expect(arg.file!.name).toBe("notes.md");
    expect(arg.tier).toBe("full");
    expect(arg.collection).toBeUndefined();
    const link = await screen.findByRole("link", { name: /Review the proposal/ });
    expect(link).toHaveAttribute("href", "/proposals/p9");
    const card = screen.getByLabelText("Ingest progress");
    expect(within(card).getByText("raw/web-clips/notes.md")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ingest another" })).toBeInTheDocument();
  });

  it("sends a pasted address after Use, and the triage choices change the payload", async () => {
    const { startIngest } = setup();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Web address"), "https://example.org/paper");
    await user.click(screen.getByRole("button", { name: "Use" }));
    expect(await screen.findByText("https://example.org/paper")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Easy/ }));
    await user.type(screen.getByLabelText(/Collection/), "series-rl");
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(startIngest).toHaveBeenCalledWith({ url: "https://example.org/paper", tier: "easy", collection: "series-rl", backend: undefined }));
    expect(document.querySelectorAll("datalist option")).toHaveLength(1); // only the collection page, not the idea
  });

  it("refuses a bad address and an unsupported file in plain words, without calling the server", async () => {
    const { startIngest } = setup();
    const user = userEvent.setup({ applyAccept: false });
    await user.type(await screen.findByLabelText("Web address"), "not a link");
    await user.click(screen.getByRole("button", { name: "Use" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("does not look like a web address");
    await user.upload(screen.getByLabelText("Choose a file"), new File(["MZ"], "tool.exe"));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot be ingested here");
    expect(screen.queryByRole("button", { name: "Ingest" })).toBeNull();
    expect(startIngest).not.toHaveBeenCalled();
  });

  it("shows a server refusal inline and keeps the form", async () => {
    setup({ startIngest: async () => { throw new Error("This knowledge base is read-only."); } });
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Choose a file"), note());
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("read-only");
    expect(screen.getByRole("button", { name: "Ingest" })).toBeEnabled();
  });
});

describe("triage", () => {
  it("says what was dropped, its kind and folder, and sends the picked backend", async () => {
    const { startIngest } = setup();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Choose a file"), new File(["%PDF"], "paper.pdf", { type: "application/pdf" }));
    const summary = await screen.findByTestId("source-summary");
    expect(summary).toHaveTextContent("paper.pdf");
    expect(summary).toHaveTextContent("PDF document");
    expect(summary).toHaveTextContent("raw/printed-docs/");
    await user.click(screen.getByRole("radio", { name: "Batch" }));
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(startIngest.mock.calls[0]![0].backend).toBe("batch"));
  });

  it("Listed makes no model call, so no backend is sent", async () => {
    const { startIngest } = setup();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Choose a file"), note());
    await user.click(screen.getByRole("radio", { name: "Batch" }));
    await user.click(screen.getByRole("radio", { name: /Listed/ }));
    expect(screen.getByRole("radio", { name: "Batch" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(startIngest).toHaveBeenCalledTimes(1));
    expect(startIngest.mock.calls[0]![0].backend).toBeUndefined();
  });

  it("the single layout keeps the progress card in view before the job starts", async () => {
    setup();
    const card = await screen.findByLabelText("Ingest progress");
    expect(card).toHaveTextContent("Shows here once you start.");
    expect(document.querySelector("[data-layout=single]")).not.toBeNull();
  });
});

describe("job card", () => {
  it("falls back to polling when the stream cannot be opened, and says a failure calmly", async () => {
    const getIngestJob = vi.fn(async () => job(["skipped", "done", "failed"], { status: "failed", error: "The model could not be reached; try again." }));
    setup({ ingestEvents: async () => { throw new Error("no stream"); }, getIngestJob });
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Choose a file"), note());
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    expect(await screen.findByText(/could not be reached; try again\./)).toBeInTheDocument();
    expect(screen.getByText("Nothing was added to your pages.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start over" })).toBeInTheDocument();
    expect(getIngestJob).toHaveBeenCalled();
    expect(screen.queryByRole("link", { name: /proposal/ })).toBeNull();
  });
});

describe("wizard layout", () => {
  it("shows one step at a time", async () => {
    act(() => setVariant("ingest-layout", "wizard"));
    const { startIngest } = setup();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Choose a file"), note());
    expect(screen.queryByRole("button", { name: "Ingest" })).toBeNull();
    expect(screen.queryByLabelText("Ingest progress")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.queryByLabelText("Choose a file")).toBeNull();
    await user.click(screen.getByRole("radio", { name: /Deep/ }));
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(startIngest).toHaveBeenCalledTimes(1));
    expect(startIngest.mock.calls[0]![0].tier).toBe("deep");
    expect(await screen.findByRole("link", { name: /Review the proposal/ })).toBeInTheDocument();
    expect(screen.queryByRole("radio")).toBeNull();
  });
});
