import { ApiError } from "./datasource";
import { createHttpDataSource } from "./http";

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

const urlOf = (f: { mock: { calls: unknown[][] } }) => (f.mock.calls[0]?.[0] as Request).url;

describe("http DataSource", () => {
  it("fetches /api/lifecycle", async () => {
    const f = vi.fn((..._a: unknown[]) => json({ version: "0.13.1" }));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    expect((await ds.getLifecycle()).version).toBe("0.13.1");
    expect(urlOf(f)).toMatch(/\/api\/lifecycle$/);
  });
  it("turns HTTP errors into ApiError with the status", async () => {
    const ds = createHttpDataSource((() => json({}, 500)) as unknown as typeof fetch);
    await expect(ds.getLifecycle()).rejects.toMatchObject({ name: "ApiError", status: 500 });
  });
  it("turns network failures into ApiError", async () => {
    const ds = createHttpDataSource((() => Promise.reject(new Error("down"))) as unknown as typeof fetch);
    await expect(ds.getShareStatus()).rejects.toBeInstanceOf(ApiError);
  });
  it("returns graph nodes as the backend emits them (layer, type, depth)", async () => {
    const nodes = [
      { id: "theme-quantum", title: "Quantum", layer: "concept", type: "topic", status: "seed", depth: "", areas: ["quantum"] },
      { id: "paper-x", title: "X", layer: "source", type: "paper", status: "digested", depth: "full", areas: [] },
    ];
    const f = vi.fn((..._a: unknown[]) => json({ nodes }));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    expect(await ds.getGraphNodes()).toEqual(nodes);
    expect(urlOf(f)).toMatch(/\/api\/graph$/);
  });
});

describe("http DataSource, other groups", () => {
  it("sends typed query and path params", async () => {
    const f = vi.fn((..._a: unknown[]) => json({ hits: [], total: 0 }));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    await ds.search("tensor rank", 5);
    expect(urlOf(f)).toMatch(/\/api\/search\?q=tensor(%20|\+)rank&limit=5$/);
    f.mockClear();
    await ds.getPage("paper-x").catch(() => {});
    expect(urlOf(f)).toMatch(/\/api\/pages\/paper-x$/);
  });
  it("posts a JSON body", async () => {
    const f = vi.fn((..._a: unknown[]) => json({ ok: true, slug: "s" }));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    await ds.saveScope({ create: true, slug: "s", title: "S", why: "", paths: [] });
    const req = f.mock.calls[0]?.[0] as Request;
    expect(req.method).toBe("POST");
    expect(await req.json()).toMatchObject({ slug: "s" });
  });
  it("surfaces the backend's error message", async () => {
    const ds = createHttpDataSource((() => json({ error: "no such page" }, 404)) as unknown as typeof fetch);
    await expect(ds.getPage("nope")).rejects.toMatchObject({ message: "no such page", status: 404 });
  });
  it("streams chat as the raw response", async () => {
    const f = vi.fn((..._a: unknown[]) => Promise.resolve(new Response("data: x\n\n", { status: 200 })));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    const res = await ds.chatStream({ question: "hi", history: [] });
    expect(await res.text()).toContain("data: x");
    expect(f.mock.calls[0]?.[0]).toBe("/api/chat");
  });
});

describe("chatStream errors", () => {
  const body = { question: "q" } as unknown as Parameters<ReturnType<typeof createHttpDataSource>["chatStream"]>[0];
  it("puts the backend's error and hint in the message", async () => {
    const ds = createHttpDataSource((() => json({ error: "No API key.", hint: "Add one in Settings." }, 400)) as unknown as typeof fetch);
    await expect(ds.chatStream(body)).rejects.toMatchObject({ name: "ApiError", status: 400, message: "No API key. Add one in Settings." });
  });
  it("falls back to the status when the body is not JSON", async () => {
    const ds = createHttpDataSource((() => Promise.resolve(new Response("oops", { status: 502 }))) as unknown as typeof fetch);
    await expect(ds.chatStream(body)).rejects.toMatchObject({ status: 502, message: "/api/chat answered 502" });
  });
});
