import { ApiError } from "./datasource";
import { createHttpDataSource } from "./http";

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

describe("http DataSource", () => {
  it("fetches /api/lifecycle", async () => {
    const f = vi.fn((..._a: unknown[]) => json({ version: "0.13.1" }));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    expect((await ds.getLifecycle()).version).toBe("0.13.1");
    expect(f.mock.calls[0]?.[0]).toBe("/api/lifecycle");
  });
  it("turns HTTP errors into ApiError with the status", async () => {
    const ds = createHttpDataSource((() => json({}, 500)) as unknown as typeof fetch);
    await expect(ds.getLifecycle()).rejects.toMatchObject({ name: "ApiError", status: 500 });
  });
  it("turns network failures into ApiError", async () => {
    const ds = createHttpDataSource((() => Promise.reject(new Error("down"))) as unknown as typeof fetch);
    await expect(ds.getShareStatus()).rejects.toBeInstanceOf(ApiError);
  });
  it("translates graph nodes to the data model at the boundary", async () => {
    const nodes = [
      { slug: "theme-quantum", title: "Quantum", type: "theme", status: "seed", areas: ["quantum"] },
      { slug: "paper-x", type: "paper", status: "digested", depth: "full" },
      { slug: "scope-a", type: "scope" },
    ];
    const ds = createHttpDataSource((() => json({ nodes })) as unknown as typeof fetch);
    const out = await ds.getGraphNodes();
    expect(out.map((n) => [n.slug, n.type, n.kind, n.depth])).toEqual([
      ["theme-quantum", "concept", "topic", undefined],
      ["paper-x", "source", "paper", "full"],
    ]);
  });
});
