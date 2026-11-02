vi.mock("@/share/env", () => ({ SHARE_PROFILE: "private", IS_SHARE: true }));

import { KV_MISSING, writeFlag } from "./api";

const res = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });

describe("writeFlag on the private site", () => {
  it("uses the owner sign-in (X-KB-Admin, same-origin), no token", async () => {
    const f = vi.fn(async () => res(200, { overrides: { "ui.system-flags-tab": true } }));
    expect(await writeFlag("ui.system-flags-tab", true, f as never)).toEqual({ ok: true, overrides: { "ui.system-flags-tab": true } });
    const init = (f.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.headers).toMatchObject({ "X-KB-Admin": "1" });
    expect(init.headers).not.toHaveProperty("X-KB-Owner-Token");
    expect(init.credentials).toBe("same-origin");
  });

  it("503 → KV not configured", async () => {
    const r = await writeFlag("ui.system-flags-tab", true, (async () => res(503, { error: "flags not configured" })) as never);
    expect(r).toEqual({ ok: false, status: 503, message: KV_MISSING });
  });
});
