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
  it("returns graph nodes as the backend emits them (layer, type, depth)", async () => {
    const nodes = [
      { id: "theme-quantum", title: "Quantum", layer: "concept", type: "topic", status: "seed", depth: "", areas: ["quantum"] },
      { id: "paper-x", title: "X", layer: "source", type: "paper", status: "digested", depth: "full", areas: [] },
    ];
    const f = vi.fn((..._a: unknown[]) => json({ nodes }));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    expect(await ds.getGraphNodes()).toEqual(nodes);
    expect(f.mock.calls[0]?.[0]).toBe("/api/graph");
  });
});
