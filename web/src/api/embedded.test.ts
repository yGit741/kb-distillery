import { describe, expect, it } from "vitest";
import { ApiError, createEmbeddedDataSource } from "@/api";
import { makeFixtureBlob } from "@/share/fixture";
import { readBlob } from "@/share/blob";
import { mockDataSource } from "@/test/datasource";

const blob = makeFixtureBlob();
const ds = createEmbeddedDataSource(blob);

describe("embedded DataSource", () => {
  it("serves the graph, its nodes and the page index from the blob", async () => {
    expect(ds.kind).toBe("embedded");
    expect(await ds.getGraph()).toBe(blob.graph);
    expect((await ds.getGraphNodes()).map((n) => n.id).sort()).toEqual(Object.keys(blob.pages).sort());
    expect((await ds.listPages()).pages).toHaveLength(Object.keys(blob.pages).length);
  });

  it("ignores the raw layer option (there is no data layer in a shared build)", async () => {
    expect(await ds.getGraph({ raw: true })).toBe(blob.graph);
  });

  it("returns one page, and 404s an unknown slug", async () => {
    expect((await ds.getPage("tensor-rank")).card.title).toBe("Tensor rank");
    await expect(ds.getPage("nope")).rejects.toMatchObject({ status: 404 });
    await expect(ds.getPage("nope")).rejects.toBeInstanceOf(ApiError);
  });

  it("searches and finds paths", async () => {
    expect((await ds.search("matrix", 3)).hits.length).toBeLessThanOrEqual(3);
    expect((await ds.findPath("tensor-rank", "matrix-rank")).distance).toBe(1);
    await expect(ds.findPath("tensor-rank", "nope")).rejects.toMatchObject({ status: 404 });
  });

  it("has no share chip and no citations unless the blob carries them", async () => {
    expect(await ds.getShareStatus()).toEqual({ status: null, chip: null });
    await expect(ds.getCitations()).rejects.toMatchObject({ status: 404 });
    const withCitations = createEmbeddedDataSource({ ...blob, citations: { nodes: [], links: [] } as never });
    expect(await withCitations.getCitations()).toEqual({ nodes: [], links: [] });
  });

  it("serves the lifecycle snapshot only when present, filling the local-only policy flag", async () => {
    await expect(ds.getLifecycle()).rejects.toMatchObject({ status: 404 });
    const life = { generated_at: "t", branch: "main", head: "abc", next_version: "1.0.1", schema: { version: "1.0", applied: [], pending: [] }, policy: { mode: "x", strict: false }, timeline: [], snapshots: [], stats: { kb_steps: 0, pr_merges: 0, ops_30d: {}, undone: 0 } };
    const priv = createEmbeddedDataSource({ ...blob, lifecycle: life as never });
    const got = await priv.getLifecycle();
    expect(got.head).toBe("abc");
    expect(got.policy.hooks_installed).toBe(false);
    expect(got.working ?? null).toBeNull();
  });

  it("rejects everything that is not part of the read-only share with a 404", async () => {
    const calls: Array<() => Promise<unknown>> = [
      () => ds.getHealth(), () => ds.getOps(), () => ds.getPipeline(), () => ds.getCorpus(), () => ds.getRawPreview("raw/x.pdf"),
      () => ds.digestRaw("raw/x.pdf"), () => ds.listScopes(), () => ds.getScope("s"), () => ds.resolveScope({ nodes: [] } as never),
      () => ds.saveScope({} as never), () => ds.deleteScope("s"), () => ds.duplicateScope("s", {} as never),
      () => ds.getChatStatus(), () => ds.getChatSettings(), () => ds.updateChatSettings({} as never), () => ds.getChatPrompts(),
      () => ds.getChatKeys(), () => ds.addChatKey({} as never), () => ds.removeChatKey("k"), () => ds.saveChat({} as never), () => ds.sendChatMessage({} as never),
      () => ds.chatStream({} as never), () => ds.listSessions(), () => ds.getSession("s"), () => ds.putSession("s", {} as never),
      () => ds.renameSession("s", "t"), () => ds.deleteSession("s"),
    ];
    for (const c of calls) await expect(c()).rejects.toMatchObject({ status: 404 });
  });

  it("without a blob every method rejects (and the shared test mock stays opt-in)", async () => {
    const none = createEmbeddedDataSource(undefined);
    await expect(none.getGraph()).rejects.toBeInstanceOf(ApiError);
    await expect(mockDataSource().listPages()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("readBlob", () => {
  it("parses #kb-data, tolerating the \\u003c escapes the builder writes, and returns null without it", () => {
    document.body.innerHTML = "";
    expect(readBlob()).toBeNull();
    const el = document.createElement("script");
    el.type = "application/json";
    el.id = "kb-data";
    el.textContent = JSON.stringify({ graph: { nodes: [] }, pages: { a: { markdown: "x <\/script> y" } } }).replace(/<\//g, "\\u003c/");
    document.head.appendChild(el);
    const got = readBlob();
    expect((got!.pages["a"] as { markdown: string }).markdown).toBe("x </script> y");
    el.remove();
  });
});
