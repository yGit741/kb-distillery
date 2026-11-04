import { createMemoryHistory } from "@tanstack/react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import type { DataSource } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { AddKnowledgeBase } from "./AddKnowledgeBase";
import { createSiteImportAdapter } from "./siteAdapter";

// the private share build: its data is baked in (embedded) and the Worker's inbox takes the bundle
vi.mock("@/share/env", () => ({ SHARE_PROFILE: "private", IS_SHARE: true }));

const reply = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const ITEM = "20261104T101500Z-0a1b2c3d";
const zip = () => new File(["x"], "my-notes.zip", { type: "application/zip" });

/** A tiny stand-in for the Worker's two routes. */
function worker(over: { validate?: () => Promise<Response>; create?: () => Promise<Response> } = {}) {
  return vi.fn((url: string) =>
    url.startsWith("/api/inbox/validate")
      ? (over.validate ?? (() => reply(200, { ok: true, kind: "zip", id: "my-notes", pages: 3, errors: [], warnings: [] })))()
      : (over.create ?? (() => reply(201, { item: ITEM, status: "pending", kind: "zip", pages: 3, errors: [], warnings: [] })))(),
  );
}

function dialog(f: ReturnType<typeof worker>) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <AddKnowledgeBase adapter={createSiteImportAdapter(f as unknown as typeof fetch)} open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

describe("Add knowledge base on the site (inbox adapter)", () => {
  it("zip, preview, Create, then the Received card with the inbox item id and no link", async () => {
    const f = worker();
    dialog(f);
    await userEvent.upload(await screen.findByTestId("kb-zip-input"), zip());
    expect(await screen.findByText(/3 pages/)).toBeInTheDocument();
    expect(screen.getByText("No problems found.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("Received")).toBeInTheDocument();
    expect(screen.getByText(/Your bundle is in the inbox/)).toHaveTextContent("It appears after your Mac's next sync.");
    expect(screen.getByText(ITEM)).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
    const urls = f.mock.calls.map((c) => c[0]);
    expect(urls[0]).toBe("/api/inbox/validate?name=my-notes.zip");
    expect(urls[urls.length - 1]).toBe("/api/inbox?name=my-notes.zip&id=my-notes");
  });

  it("validation errors from the Worker block Create", async () => {
    dialog(worker({ validate: () => reply(200, { ok: false, kind: "zip", id: "my-notes", pages: 2, errors: ["a.md: [links] broken link"], warnings: [] }) }));
    await userEvent.upload(await screen.findByTestId("kb-zip-input"), zip());
    expect(await screen.findByText(/broken link/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
  });

  it("a non-owner gets the plain 403 sentence on step 1", async () => {
    dialog(worker({ validate: () => reply(403, { error: "not allowed" }) }));
    await userEvent.upload(await screen.findByTestId("kb-zip-input"), zip());
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the site owner can add knowledge bases here.");
  });

  it("a failed submit stays on the preview with the message", async () => {
    dialog(worker({ create: () => reply(503, { error: "inbox not configured: bind an R2 bucket as KB_INBOX (see publish.md)" }) }));
    await userEvent.upload(await screen.findByTestId("kb-zip-input"), zip());
    await userEvent.click(await screen.findByRole("button", { name: "Create" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/inbox not configured/);
    expect(screen.queryByText("Received")).toBeNull();
  });
});

describe("header entry in the private share build", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("a + button next to the title opens the dialog, for an owner whose inbox is set up", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ owner: true, inbox: true }), { status: 200 })));
    const ds: DataSource = { ...mockDataSource({ getShareStatus: async () => ({ status: null, chip: null }) }), kind: "embedded" };
    render(<App source={ds} router={createAppRouter(createMemoryHistory({ initialEntries: ["/"] }), "")} />);
    const header = await screen.findByRole("banner");
    await userEvent.click(await within(header).findByRole("button", { name: "Add knowledge base" }));
    expect(await screen.findByRole("dialog", { name: "Add knowledge base" })).toBeInTheDocument();
  });
});
