import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { DataSourceProvider, type DataSource } from "@/api";
import type { IngestInput, IngestJob, IngestListItem } from "@/api/types";
import { setVariant } from "@/components/variants";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import IngestScreen from "./index";

const STEPS = ["fetch", "convert", "digest", "propose"];
const job = (states: string[], over: Partial<IngestJob> = {}): IngestJob => ({
  id: "j1", status: "running", source: "notes.md", kind: "file", tier: "full", collection: "", backend: "", started: 1_700_000_000, finished: null, step: "fetch",
  pages: [], proposal_id: null, error: null,
  steps: STEPS.map((name, i) => ({ name, state: states[i] ?? "pending", detail: name === "convert" && states[1] === "done" ? "raw/web-clips/notes.md" : "" })),
  ...over,
});

/** A row of GET /api/ingest. */
const item = (id: string, over: Partial<IngestListItem> = {}): IngestListItem => ({
  ...job(["skipped", "done", "done", "done"], { id, status: "done", proposal_id: `p-${id}`, pages: ["a", "b"], finished: 1_700_000_100 }),
  proposal_status: "open", proposal_updated: null, ...over,
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
  const listed: IngestListItem[] = [];                      // what the server would list after each start
  const startIngest = vi.fn(async (input: IngestInput) => {
    const id = `j${listed.length + 1}`;
    listed.unshift(item(id, { status: "running", source: input.file?.name ?? input.url ?? "", proposal_id: null, proposal_status: null, pages: [], finished: null }));
    return { job_id: id };
  });
  const ds = mockDataSource({
    startIngest,
    listIngest: async () => [...listed],
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
    const row = await screen.findByTestId("ingest-row");              // the row is there at once, with the form cleared
    expect(row).toHaveTextContent("notes.md");
    expect(screen.queryByTestId("source-summary")).toBeNull();
    expect(screen.getByLabelText("Choose a file")).toBeInTheDocument();
  });

  it("sends a pasted address after Use, and the triage choices change the payload", async () => {
    const { startIngest } = setup();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Web address"), "https://example.org/paper");
    await user.click(screen.getByRole("button", { name: "Use" }));
    expect(await screen.findByText("https://example.org/paper")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Easy/ }));
    await user.type(screen.getByLabelText(/Collection/), "series-rl");
    expect(document.querySelectorAll("datalist option")).toHaveLength(1); // only the collection page, not the idea
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(startIngest).toHaveBeenCalledWith({ url: "https://example.org/paper", tier: "easy", collection: "series-rl", backend: undefined }));
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
    // a paper is filed by its year and this name has none: Ingest waits for it
    expect(screen.getByRole("button", { name: "Ingest" })).toBeDisabled();
    await user.type(screen.getByLabelText("Year of the paper"), "2019");
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(startIngest.mock.calls[0]![0].backend).toBe("batch"));
    expect(startIngest.mock.calls[0]![0].year).toBe("2019");
  });

  it("asks no year when the name has one or for a note, and does not insist on it for a member of a collection", async () => {
    const { startIngest } = setup();
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Choose a file"), new File(["%PDF"], "2019-paper.pdf", { type: "application/pdf" }));
    await screen.findByTestId("source-summary");
    expect(screen.queryByTestId("year-field")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Change" }));
    await user.upload(await screen.findByLabelText("Choose a file"), note());
    await screen.findByTestId("source-summary");
    expect(screen.queryByTestId("year-field")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Change" }));
    await user.upload(await screen.findByLabelText("Choose a file"), new File(["%PDF"], "lecture-3.pdf", { type: "application/pdf" }));
    expect(await screen.findByTestId("year-field")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ingest" })).toBeDisabled();
    // a member of a collection is filed by the collection: the year stays on offer but no longer holds Ingest back
    await user.type(screen.getByLabelText(/Collection/), "course-ml");
    expect(screen.getByTestId("year-field")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ingest" }));
    await waitFor(() => expect(startIngest).toHaveBeenCalledTimes(1));
    expect(startIngest.mock.calls[0]![0].year).toBeUndefined();
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

  it("the single layout is the form with the inbox under it", async () => {
    setup();
    expect(await screen.findByLabelText("Choose a file")).toBeInTheDocument();
    expect(document.querySelector("[data-layout=single]")).not.toBeNull();
    expect(screen.queryByLabelText("Ingest progress")).toBeNull();
  });
});

describe("job card (wizard)", () => {
  it("falls back to polling when the stream cannot be opened, and says a failure calmly", async () => {
    act(() => setVariant("ingest-layout", "wizard"));
    const getIngestJob = vi.fn(async () => job(["skipped", "done", "failed"], { status: "failed", error: "The model could not be reached; try again." }));
    setup({ ingestEvents: async () => { throw new Error("no stream"); }, getIngestJob });
    const user = userEvent.setup();
    await user.upload(await screen.findByLabelText("Choose a file"), note());
    await user.click(screen.getByRole("button", { name: "Next" }));
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


describe("the inbox of ingests", () => {
  const rows: IngestListItem[] = [
    item("r1", { status: "running", proposal_id: null, proposal_status: null, pages: [], finished: null, source: "https://example.org/live", kind: "url", step: "digest",
      steps: STEPS.map((name, i) => ({ name, state: i < 2 ? "done" : i === 2 ? "active" : "pending", detail: i === 2 ? "reading with the default backend" : "" })) }),
    item("r2", { source: "waiting.pdf", proposal_status: "open" }),
    item("r3", { source: "kept.md", proposal_status: "applied", proposal_updated: "2026-11-09T10:00:00+00:00" }),
    item("r4", { source: "turned-down.md", proposal_status: "rejected" }),
    item("r5", { source: "https://example.org/broken", kind: "url", tier: "easy", status: "failed", proposal_id: null, proposal_status: null, pages: [], error: "that address could not be found", step: "fetch" }),
    item("r6", { source: "paper.pdf", status: "interrupted", proposal_id: null, proposal_status: null, pages: [], error: "the server stopped while this was running" }),
  ];

  it("ui.edit-preview on: a waiting row opens its plan over the graph", () =>
    withFlag("ui.edit-preview", true, async () => {
      setup({ listIngest: async () => rows });
      const waiting = (await screen.findByText("waiting.pdf")).closest("a");
      expect(waiting?.getAttribute("href")).toContain("/graph?preview=p-r2");
    }));

  it("lists each group, hides the empty ones, and links a waiting row to its review", () => withFlag("ui.edit-preview", false, async () => {
    setup({ listIngest: async () => rows, ingestEvents: async () => sse([["job", job(["done", "done", "active"], { id: "r1", step: "digest" })]]) });
    const names = async () => (await screen.findAllByRole("heading", { level: 2 })).map((h) => h.textContent);
    expect(await names()).toEqual(["In progress", "Waiting for your review", "Done", "Did not finish"]);
    const waiting = screen.getByText("waiting.pdf").closest("a");
    expect(waiting).toHaveAttribute("href", "/proposals/p-r2");
    const done = screen.getAllByTestId("ingest-row").filter((r) => r.dataset.group === "done");
    expect(done[0]).toHaveTextContent("Applied");
    expect(done[1]).toHaveTextContent("Rejected");
    expect(within(done[0]!).getByText("kept.md")).toBeInTheDocument();
  }));

  it("shows a running row live with its step", async () => {
    setup({ listIngest: async () => [rows[0]!], ingestEvents: async () => sse([["job", job(["done", "done", "active"], { id: "r1", step: "digest", steps: STEPS.map((name, i) => ({ name, state: i < 2 ? "done" : i === 2 ? "active" : "pending", detail: i === 2 ? "reading with the api backend" : "" })) })]]) });
    const row = await screen.findByTestId("ingest-row");
    expect(row).toHaveTextContent("Working");
    await waitFor(() => expect(row).toHaveTextContent("Digesting · reading with the api backend"));
  });

  it("says why one did not finish; Try again re-sends a web address, a file is dropped again", async () => {
    const { startIngest } = setup({ listIngest: async () => rows.slice(4) });
    const user = userEvent.setup();
    const broken = (await screen.findByText("https://example.org/broken")).closest("li")!;
    expect(broken).toHaveTextContent("That address could not be found");
    expect(broken).toHaveTextContent("Stopped");
    const interrupted = screen.getByText("paper.pdf").closest("li")!;
    expect(interrupted).toHaveTextContent("Interrupted");
    expect(interrupted).toHaveTextContent("Drop the file again");
    expect(within(interrupted).queryByRole("button", { name: "Try again" })).toBeNull();
    await user.click(within(broken).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(startIngest).toHaveBeenCalledWith({ url: "https://example.org/broken", tier: "easy", collection: undefined, backend: undefined }));
  });

  it("starting adds a row at once and a second one can follow while the first runs", async () => {
    const { startIngest } = setup({ ingestEvents: async () => new Promise<Response>(() => {}) });
    const user = userEvent.setup();
    for (const name of ["one.md", "two.md"]) {
      await user.upload(await screen.findByLabelText("Choose a file"), new File(["# x"], name, { type: "text/markdown" }));
      await user.click(screen.getByRole("button", { name: "Ingest" }));
      await waitFor(() => expect(screen.getAllByTestId("ingest-row").some((r) => r.textContent?.includes(name))).toBe(true));
    }
    expect(startIngest).toHaveBeenCalledTimes(2);
    expect(screen.getAllByTestId("ingest-row")).toHaveLength(2);
  });

  it("has a modest empty state and an error with a retry", async () => {
    setup();
    expect(await screen.findByText("Nothing brought in yet. What you add shows up here.")).toBeInTheDocument();
  });

  it("says plainly when the list cannot be loaded", async () => {
    setup({ listIngest: async () => { throw new Error("down"); } });
    expect(await screen.findByText("Could not load your ingests.")).toBeInTheDocument();
  });
});
