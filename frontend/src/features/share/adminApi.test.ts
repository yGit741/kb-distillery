import { AdminError, createAdminClient, explain } from "./adminApi";

const res = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

describe("admin client", () => {
  it("sends the cookie flow and the CSRF header", async () => {
    const f = vi.fn(async () => res(200, { snapshots: [], main: { kb_version: null }, notes: [] }));
    await createAdminClient(f).listSnapshots();
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/admin/api/snapshots");
    expect(init.method).toBe("GET");
    expect(init.credentials).toBe("same-origin");
    expect((init.headers as Record<string, string>)["X-KB-Admin"]).toBe("1");
  });

  it("deletes with the typed confirmation in the body", async () => {
    const f = vi.fn(async () => res(200, { deleted: "snapshot-20261001-x", url: "u" }));
    const r = await createAdminClient(f).deleteSnapshot("snapshot-20261001-x", "snapshot-20261001-x");
    expect(r.deleted).toBe("snapshot-20261001-x");
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/admin/api/snapshots/snapshot-20261001-x");
    expect(init.method).toBe("DELETE");
    expect(JSON.parse(init.body as string)).toEqual({ confirm: "snapshot-20261001-x" });
  });

  it("posts prune and maps errors by status", async () => {
    const f = vi.fn(async () => res(503, { error: "panel not configured: set CF_API_TOKEN" }));
    const err = await createAdminClient(f).prunePlan().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(AdminError);
    expect(explain(err).kind).toBe("setup");
    expect(explain(new AdminError(401, "sign in first")).kind).toBe("signed-out");
    expect(explain(new AdminError(403, "not an admin")).kind).toBe("forbidden");
  });

  it("turns a network failure into status 0", async () => {
    const f = vi.fn(async () => { throw new Error("boom"); });
    await expect(createAdminClient(f).listSnapshots()).rejects.toMatchObject({ status: 0 });
  });
});
