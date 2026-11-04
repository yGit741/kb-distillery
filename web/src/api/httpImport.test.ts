import { createHttpDataSource } from "./http";

const json = (body: unknown, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

describe("http DataSource: knowledge base import", () => {
  it("posts a zip as multipart with the id", async () => {
    const f = vi.fn((..._a: unknown[]) => json({ id: "x", name: "X", source: "x.zip", pages: 1, errors: [], warnings: [], ref: "", commit: "", ok: true }));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    await ds.previewKbImport({ file: new File(["z"], "x.zip"), id: "x" });
    const [path, init] = f.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/kb/import/validate");
    expect(init.method).toBe("POST");
    const form = init.body as FormData;
    expect((form.get("file") as File).name).toBe("x.zip");
    expect(form.get("id")).toBe("x");
  });

  it("posts a git URL as JSON", async () => {
    const f = vi.fn((..._a: unknown[]) => json({ id: "n", name: "N", root: "/b/n", pages: 2 }));
    const ds = createHttpDataSource(f as unknown as typeof fetch);
    expect((await ds.importKb({ gitUrl: "https://example.com/n.git" })).id).toBe("n");
    const [path, init] = f.mock.calls[0] as [string, RequestInit];
    expect(path).toBe("/api/kb/import");
    expect(JSON.parse(init.body as string)).toEqual({ git_url: "https://example.com/n.git", id: null, kit: null });
  });

  it("surfaces the server message of a 422", async () => {
    const ds = createHttpDataSource((() => json({ detail: "not a readable zip" }, 422)) as unknown as typeof fetch);
    await expect(ds.importKb({ file: new File(["z"], "x.zip") })).rejects.toMatchObject({ message: "not a readable zip", status: 422 });
  });
});
