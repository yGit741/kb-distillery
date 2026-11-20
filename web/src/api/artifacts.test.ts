import { describe, expect, it, vi } from "vitest";
import { createEmbeddedDataSource } from "./embedded";
import { createHttpDataSource } from "./http";
import { makeFixtureBlob } from "@/share/fixture";
import type { ArtifactGraph } from "./artifacts";

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
const graph: ArtifactGraph = { nodes: [{ id: "repo:r", type: "Repo", name: "r" }], links: [], cites: {} };

describe("getArtifacts", () => {
  it("http: asks /api/artifacts for the picked knowledge base", async () => {
    const f = vi.fn((..._a: unknown[]) => json(graph));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    expect((await ds.getArtifacts({ kb: "code" }))?.nodes[0]?.id).toBe("repo:r");
    expect((f.mock.calls[0]?.[0] as Request).url).toMatch(/\/api\/artifacts\?kb=code$/);
  });

  it("http: a 404 is no layer (null), any other failure is an error", async () => {
    const none = createHttpDataSource((() => json({ detail: "no artifact layer" }, 404)) as unknown as typeof fetch);
    expect(await none.getArtifacts()).toBeNull();
    const broken = createHttpDataSource((() => json({}, 500)) as unknown as typeof fetch);
    await expect(broken.getArtifacts()).rejects.toMatchObject({ name: "ApiError", status: 500 });
  });

  it("embedded: the baked layer, or null when the build baked none", async () => {
    expect(await createEmbeddedDataSource(makeFixtureBlob()).getArtifacts()).toBeNull();
    expect(await createEmbeddedDataSource({ ...makeFixtureBlob(), artifacts: graph }).getArtifacts()).toEqual(graph);
  });
});
