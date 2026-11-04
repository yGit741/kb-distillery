import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryHistory } from "@tanstack/react-router";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { createEmbeddedDataSource } from "@/api";

// the private share build: embedded data, the Worker answers /api
vi.mock("@/share/env", () => ({ SHARE_PROFILE: "private", IS_SHARE: true }));

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const PROBE = /^\/api\/inbox\/\d{8}T\d{6}Z-[0-9a-f]{8}$/;

/** The Worker as the site sees it: `probe` is its answer to the owner probe, the rest is the inbox. */
function worker(probe: Response | (() => Promise<Response>)) {
  const f = vi.fn(async (url: string, init?: RequestInit) => {
    if (PROBE.test(url)) return typeof probe === "function" ? probe() : probe.clone();
    if (url.startsWith("/api/inbox/validate")) return json(200, { ok: false, kind: "zip", id: "my-notes", pages: 2, errors: ["a.md: [links] broken link"], warnings: [] });
    if (url.startsWith("/api/inbox") && init?.method === "POST") return json(201, { item: "x", status: "pending" });
    return json(404, { error: "no such route" });
  });
  vi.stubGlobal("fetch", f);
  return f;
}

function site() {
  const router = createAppRouter(createMemoryHistory({ initialEntries: ["/start"] }), "");
  render(<App source={createEmbeddedDataSource()} router={router} />);
}
const entry = () => screen.queryByRole("button", { name: "Add knowledge base" });

describe("Add knowledge base on the deployed site", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("an owner sees the entry beside the title and the dialog ends in Received", async () => {
    const f = worker(json(404, { error: "no such inbox item" }));
    site();
    await userEvent.click(await screen.findByRole("button", { name: "Add knowledge base" }));
    expect(await screen.findByText("Import an OKF bundle as a new knowledge base. Your current one is not changed.")).toBeInTheDocument();
    await userEvent.upload(await screen.findByTestId("kb-zip-input"), new File(["z"], "my-notes.zip", { type: "application/zip" }));
    expect(await screen.findByText("a.md: [links] broken link")).toBeInTheDocument();       // the Worker's checker errors
    expect(screen.getByRole("button", { name: "Create" })).toBeDisabled();
    expect(f.mock.calls.some(([u]) => String(u).startsWith("/api/inbox/validate"))).toBe(true);
  });

  it("an owner can create: Received, it appears after the next sync", async () => {
    const f = worker(json(404, { error: "no such inbox item" }));
    f.mockImplementation(async (url: string, init?: RequestInit) => {
      if (PROBE.test(url)) return json(404, { error: "no such inbox item" });
      if (url.startsWith("/api/inbox/validate")) return json(200, { ok: true, kind: "zip", id: "my-notes", pages: 2, errors: [], warnings: [] });
      return init?.method === "POST" ? json(201, { item: "x", status: "pending" }) : json(404, {});
    });
    site();
    await userEvent.click(await screen.findByRole("button", { name: "Add knowledge base" }));
    await userEvent.upload(await screen.findByTestId("kb-zip-input"), new File(["z"], "my-notes.zip", { type: "application/zip" }));
    await userEvent.click(await screen.findByRole("button", { name: "Create" }));
    expect(await screen.findByText("Received")).toBeInTheDocument();
    expect(screen.getByText("Received, it appears after your Mac's next sync")).toBeInTheDocument();
  });

  it.each([
    ["a non-owner (403)", json(403, { error: "not an admin" })],
    ["a signed-out viewer (401)", json(401, { error: "sign in first" })],
    ["a site with no inbox bucket (503)", json(503, { error: "inbox not configured" })],
  ])("%s does not see it, and the header is the plain title link", async (_n, probe) => {
    const f = worker(probe);
    site();
    expect(await screen.findByRole("link", { name: "Knowledge base" })).toBeInTheDocument();
    await vi.waitFor(() => expect(f.mock.calls.some(([u]) => PROBE.test(String(u)))).toBe(true));
    await new Promise((r) => setTimeout(r, 50));
    expect(entry()).toBeNull();
  });
});
