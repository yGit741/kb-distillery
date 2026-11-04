import { createSiteImportAdapter, inboxAccess } from "./siteAdapter";

const reply = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const zip = (name = "my-notes.zip") => ({ kind: "zip" as const, file: new File(["z"], name, { type: "application/zip" }) });
const call = (f: ReturnType<typeof vi.fn>, n = 0) => f.mock.calls[n] as unknown as [string, RequestInit];
const adapterFor = (f: ReturnType<typeof vi.fn>) => createSiteImportAdapter(f as unknown as typeof fetch);

describe("site import adapter (the Worker inbox)", () => {
  it("validate posts the zip as bytes with the owner headers and maps the report", async () => {
    const f = vi.fn(() => reply(200, { ok: true, kind: "zip", id: "my-notes", pages: 3, errors: [], warnings: ["b.md: no title"] }));
    const p = await adapterFor(f).validate(zip());
    const [url, init] = call(f);
    expect(url).toBe("/api/inbox/validate?name=my-notes");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
    expect(init.headers).toMatchObject({ "X-KB-Admin": "1", "Content-Type": "application/zip" });
    expect(init.body).toBeInstanceOf(File);
    expect(p).toEqual({ id: "my-notes", name: "my-notes", pages: 3, source: "my-notes.zip", errors: [], warnings: ["b.md: no title"] });
  });

  it("validate sends an edited id as a query parameter and keeps it", async () => {
    const f = vi.fn(() => reply(200, { ok: true, kind: "zip", id: "my-notes", pages: 1, errors: [], warnings: [] }));
    const p = await adapterFor(f).validate({ ...zip(), id: "fresh" });
    expect(call(f)[0]).toBe("/api/inbox/validate?name=my-notes&id=fresh");
    expect(p.id).toBe("fresh");
  });

  it("validate with errors returns them so the dialog blocks Create", async () => {
    const f = vi.fn(() => reply(200, { ok: false, kind: "zip", id: "x", pages: 2, errors: ["a.md: [links] broken link"], warnings: [] }));
    const p = await adapterFor(f).validate(zip("x.zip"));
    expect(p.errors).toEqual(["a.md: [links] broken link"]);
  });

  it("a bundle with no pages and no findings still gets an error", async () => {
    const f = vi.fn(() => reply(200, { ok: false, kind: "zip", id: "x", pages: 0, errors: [], warnings: [] }));
    expect((await adapterFor(f).validate(zip("x.zip"))).errors).toEqual(["The bundle has no pages."]);
  });

  it("a reserved id is an error before the Worker refuses it", async () => {
    const f = vi.fn(() => reply(200, { ok: true, kind: "zip", id: "demo", pages: 1, errors: [], warnings: [] }));
    expect((await adapterFor(f).validate(zip("demo.zip"))).errors[0]).toMatch(/reserved/);
  });

  it("a git URL is posted as JSON; its name and id come from the URL", async () => {
    const f = vi.fn(() => reply(200, { ok: true, kind: "git", id: "", pages: 0, errors: [], warnings: ["a git URL is checked on the Mac when it is imported"] }));
    const p = await adapterFor(f).validate({ kind: "git", url: "https://example.com/me/My_Notes.git#main" });
    const [url, init] = call(f);
    expect(url).toBe("/api/inbox/validate");
    expect(init.headers).toMatchObject({ "Content-Type": "application/json", "X-KB-Admin": "1" });
    expect(JSON.parse(init.body as string)).toEqual({ git_url: "https://example.com/me/My_Notes.git#main" });
    expect(p).toMatchObject({ id: "my-notes", name: "My_Notes", source: "https://example.com/me/My_Notes.git#main", errors: [] });
  });

  it("submit posts to /api/inbox and answers received with the inbox item id", async () => {
    const f = vi.fn(() => reply(201, { item: "20261104T101500Z-0a1b2c3d", status: "pending", kind: "zip", pages: 3, errors: [], warnings: [] }));
    const out = await adapterFor(f).submit({ ...zip(), id: "my-notes" });
    expect(call(f)[0]).toBe("/api/inbox?name=my-notes&id=my-notes");
    expect(out).toEqual({ state: "received", message: expect.stringMatching(/inbox.*next sync/), ref: "20261104T101500Z-0a1b2c3d" });
  });

  it("submit of a git URL sends its id in the JSON", async () => {
    const f = vi.fn(() => reply(201, { item: "20261104T101500Z-0a1b2c3d" }));
    await adapterFor(f).submit({ kind: "git", url: "https://example.com/n.git", id: "n" });
    expect(JSON.parse(call(f)[1].body as string)).toEqual({ git_url: "https://example.com/n.git", id: "n" });
  });

  it("an invalid bundle at submit (422) shows the Worker's sentence", async () => {
    const f = vi.fn(() => reply(422, { error: "the bundle is not valid OKF; nothing was stored", errors: ["x"] }));
    await expect(adapterFor(f).submit(zip())).rejects.toThrow("the bundle is not valid OKF; nothing was stored");
  });

  it("a 401 says the sign-in expired", async () => {
    const f = vi.fn(() => reply(401, { error: "sign in first" }));
    await expect(adapterFor(f).validate(zip())).rejects.toThrow(/sign-in has expired/);
  });

  it("a 403 says only the owner can add", async () => {
    const f = vi.fn(() => reply(403, { error: "not an admin" }));
    await expect(adapterFor(f).submit(zip())).rejects.toThrow(/^Only the site owner can add knowledge bases here\.$/);
  });

  it("a 403 for another reason (origin, header) keeps the Worker's reason", async () => {
    const f = vi.fn(() => reply(403, { error: "cross-origin request refused" }));
    await expect(adapterFor(f).submit(zip())).rejects.toThrow("Only the site owner can add knowledge bases here. (cross-origin request refused)");
  });

  it("a 503 (no bucket yet) shows the Worker's message", async () => {
    const f = vi.fn(() => reply(503, { error: "inbox not configured: bind an R2 bucket as KB_INBOX (see publish.md)" }));
    await expect(adapterFor(f).submit(zip())).rejects.toThrow(/inbox not configured/);
  });

  it("a network error is explained", async () => {
    const f = vi.fn(() => Promise.reject(new TypeError("Failed to fetch")));
    await expect(adapterFor(f).validate(zip())).rejects.toThrow("Could not reach the site's inbox: Failed to fetch");
  });

  it("a non-JSON failure falls back to its status", async () => {
    const f = vi.fn(() => Promise.resolve(new Response("<html>bad gateway</html>", { status: 502 })));
    await expect(adapterFor(f).validate(zip())).rejects.toThrow("The site's inbox answered 502.");
  });
});

describe("inboxAccess (owner and inbox ready)", () => {
  const ask = (status: number, body: unknown) => inboxAccess(((..._a: unknown[]) => reply(status, body)) as unknown as typeof fetch);

  it("owner and inbox: yes", async () => {
    expect(await ask(200, { owner: true, inbox: true })).toBe(true);
  });
  it.each([[{ owner: false, inbox: true }], [{ owner: true, inbox: false }], [{}]])("%j: no", async (body) => {
    expect(await ask(200, body)).toBe(false);
  });
  it.each([401, 403, 404, 503])("status %i is a no", async (status) => {
    expect(await ask(status, { owner: true, inbox: true })).toBe(false);
  });
  it("a network failure is a no; the call is a plain read of /api/inbox/access", async () => {
    expect(await inboxAccess((() => Promise.reject(new Error("offline"))) as unknown as typeof fetch)).toBe(false);
    const g = vi.fn(() => reply(200, { owner: true, inbox: true }));
    await inboxAccess(g as unknown as typeof fetch);
    expect(call(g)[0]).toBe("/api/inbox/access");
    expect(call(g)[1].method).toBeUndefined();
  });
});
