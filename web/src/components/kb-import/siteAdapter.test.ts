import { createSiteImportAdapter, probeInboxOwner, RECEIVED } from "./siteAdapter";

const reply = (status: number, body: unknown) => Promise.resolve(new Response(typeof body === "string" ? body : JSON.stringify(body), { status }));
const zip = (name = "my-notes.zip") => new File(["zip-bytes"], name, { type: "application/zip" });
const report = (over: object = {}) => ({ ok: true, kind: "zip", id: "my-notes", pages: 3, errors: [], warnings: [], ...over });
const call = (f: ReturnType<typeof vi.fn>, n = 0) => f.mock.calls[n] as [string, RequestInit & { headers: Record<string, string> }];

describe("site import adapter (the Worker's inbox)", () => {
  it("validate sends the zip as the body with the owner header and maps the report to a preview", async () => {
    const f = vi.fn((..._a: unknown[]) => reply(200, report({ warnings: ["w"] })));
    const file = zip();
    const p = await createSiteImportAdapter(f as never).validate({ kind: "zip", file });
    const [url, init] = call(f);
    expect(url).toBe("/api/inbox/validate?name=my-notes");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(file);
    expect(init.credentials).toBe("same-origin");
    expect(init.headers).toMatchObject({ "X-KB-Admin": "1", "Content-Type": "application/zip" });
    expect(p).toEqual({ id: "my-notes", name: "My notes", pages: 3, source: "my-notes.zip", errors: [], warnings: ["w"] });
  });

  it("an edited id goes to the Worker and comes back unchanged, so the dialog settles", async () => {
    const f = vi.fn((..._a: unknown[]) => reply(200, report({ id: "my-notes" })));
    const p = await createSiteImportAdapter(f as never).validate({ kind: "zip", file: zip(), id: "mine" });
    expect(call(f)[0]).toBe("/api/inbox/validate?id=mine&name=my-notes");
    expect(p.id).toBe("mine");
  });

  it("the Worker's checker errors come through as the preview's errors", async () => {
    const f = vi.fn((..._a: unknown[]) => reply(200, report({ ok: false, errors: ["a.md: [links] broken link"] })));
    const p = await createSiteImportAdapter(f as never).validate({ kind: "zip", file: zip() });
    expect(p.errors).toEqual(["a.md: [links] broken link"]);
  });

  it("a bundle with no pages is an error even when the checker lists none", async () => {
    const f = vi.fn((..._a: unknown[]) => reply(200, report({ ok: false, pages: 0 })));
    expect((await createSiteImportAdapter(f as never).validate({ kind: "zip", file: zip() })).errors).toEqual(["The bundle has no pages."]);
  });

  it("a git URL is sent as JSON; its id comes from the repository name", async () => {
    const f = vi.fn((..._a: unknown[]) => reply(200, report({ kind: "git", id: "", pages: 0, warnings: ["checked on the Mac"] })));
    const p = await createSiteImportAdapter(f as never).validate({ kind: "git", url: "https://example.com/me/Reading_List.git#main" });
    const [url, init] = call(f);
    expect(url).toBe("/api/inbox/validate");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ git_url: "https://example.com/me/Reading_List.git#main" });
    expect(p).toMatchObject({ id: "reading-list", name: "Reading list", source: "https://example.com/me/Reading_List.git#main", errors: [] });
  });

  it("submit stores the bundle and answers received", async () => {
    const f = vi.fn((..._a: unknown[]) => reply(201, { item: "x", status: "pending" }));
    const o = await createSiteImportAdapter(f as never).submit({ kind: "zip", file: zip(), id: "mine" });
    expect(call(f)[0]).toBe("/api/inbox?id=mine&name=my-notes");
    expect(o).toEqual({ state: "received", message: "Received, it appears after your Mac's next sync" });
    expect(RECEIVED).toBe(o.state === "received" ? o.message : "");
  });

  it.each([
    [422, { error: "not valid OKF", errors: ["a.md: broken"] }, "a.md: broken"],
    [401, { error: "sign in first" }, "Signed out. Reload the page to sign in again."],
    [403, { error: "not an admin" }, "This account cannot add knowledge bases."],
    [503, { error: "inbox not configured" }, "The upload inbox is not set up on this site."],
    [413, { error: "upload is over the 100 byte limit" }, "upload is over the 100 byte limit"],
    [500, { error: "inbox storage failed" }, "inbox storage failed"],
  ])("submit with %i says why", async (status, body, message) => {
    const f = vi.fn((..._a: unknown[]) => reply(status, body));
    await expect(createSiteImportAdapter(f as never).submit({ kind: "zip", file: zip() })).rejects.toThrow(message);
  });

  it("an unreachable site is an error the dialog can show", async () => {
    const f = vi.fn(() => Promise.reject(new Error("offline")));
    await expect(createSiteImportAdapter(f as never).validate({ kind: "zip", file: zip() })).rejects.toThrow("Could not reach the site: offline");
  });
});

describe("probeInboxOwner (owner and inbox ready)", () => {
  const probe = (status: number, body: unknown) => probeInboxOwner(((..._a: unknown[]) => reply(status, body)) as never);

  it("404 no such inbox item: an owner, and the bucket is bound", async () => {
    expect(await probe(404, { error: "no such inbox item" })).toBe(true);
  });
  it.each([[401, "sign in first"], [403, "not an admin"], [503, "inbox not configured"]])("%i hides it", async (status, error) => {
    expect(await probe(status, { error })).toBe(false);
  });
  it("a 404 that is not the Worker's (a static host) is a no", async () => {
    expect(await probe(404, "<html>not found</html>")).toBe(false);
  });
  it("a network failure is a no, and the probe reads without writing", async () => {
    const f = vi.fn(() => Promise.reject(new Error("offline")));
    expect(await probeInboxOwner(f as never)).toBe(false);
    const g = vi.fn((..._a: unknown[]) => reply(404, { error: "no such inbox item" }));
    await probeInboxOwner(g as never);
    expect(call(g)[0]).toMatch(/^\/api\/inbox\/\d{8}T\d{6}Z-[0-9a-f]{8}$/);
    expect(call(g)[1].method).toBeUndefined();
    expect(call(g)[1].headers["X-KB-Admin"]).toBe("1");
  });
});
