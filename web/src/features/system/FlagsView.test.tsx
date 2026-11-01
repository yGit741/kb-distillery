import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { FLAG_NAMES, flag, setFlagOverrides } from "@/flags";
import { setOwnerToken } from "@/flags/api";
import { FlagsView } from "./FlagsView";
import { flagRows } from "./flagsModel";

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function mount(env: "local" | "private" | "public" = "local") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <FlagsView env={env} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  setOwnerToken(null);
  setFlagOverrides({});
});

describe("flagRows", () => {
  it("one row per registry flag; expiry warns at ≤14 days and is bad once past", () => {
    const rows = flagRows("local", {}, new Date("2027-10-15T12:00:00Z"));
    expect(rows).toHaveLength(FLAG_NAMES.length);
    const lc = rows.find((r) => r.name === "screen.lifecycle")!;
    expect(lc.expiresInDays).toBe(10);
    expect(lc.expiryTone).toBe("warn");
    expect(lc.ageDays).toBe(355);
    expect(flagRows("local", {}, new Date("2027-11-01T00:00:00Z"))[0]?.expiryTone).toBe("bad");
    expect(flagRows("local", {}, new Date("2026-10-25T00:00:00Z"))[0]?.expiryTone).toBe("");
  });

  it("overrides apply to runtime flags only", () => {
    const rows = flagRows("local", { "ui.system-flags-tab": true, "screen.lifecycle": false } as never);
    const rt = rows.find((r) => r.name === "ui.system-flags-tab")!;
    expect([rt.value, rt.source]).toEqual([true, "override"]);
    const b = rows.find((r) => r.name === "screen.lifecycle")!;
    expect([b.value, b.source]).toEqual([true, "registry"]);
  });
});

describe("FlagsView", () => {
  it("renders every flag; build flags are locked", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(200, { env: "local", flags: [], overrides: {} })));
    mount();
    expect(screen.getByTestId("flags-count")).toHaveTextContent(String(FLAG_NAMES.length));
    for (const n of FLAG_NAMES) expect(screen.getByTestId(`flag-${n}`)).toBeInTheDocument();
    expect(screen.getAllByText("change meta/flags.toml and redeploy").length).toBeGreaterThan(0);
    expect(screen.getByRole("switch", { name: "Toggle ui.system-flags-tab" })).toHaveAttribute("aria-checked", "false");
  });

  it("toggle asks for the token once, sends it, keeps it out of storage", async () => {
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === "PUT" ? (() => { const v = JSON.parse(String(init.body)).value; return json(200, { overrides: v === null ? {} : { "ui.system-flags-tab": v } }); })() : json(200, { overrides: {} }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const ask = vi.spyOn(window, "prompt").mockReturnValue("s3cret");
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    mount();
    const sw = screen.getByRole("switch", { name: "Toggle ui.system-flags-tab" });
    await userEvent.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "true"));
    expect(flag("ui.system-flags-tab")).toBe(true);
    const put = fetchMock.mock.calls.find(([, i]) => i?.method === "PUT")!;
    expect(put[0]).toBe("/api/flags/ui.system-flags-tab");
    expect((put[1]!.headers as Record<string, string>)["X-KB-Owner-Token"]).toBe("s3cret");
    await userEvent.click(sw);
    await waitFor(() => expect(sw).toHaveAttribute("aria-checked", "false"));
    expect(JSON.parse(String(fetchMock.mock.calls.filter(([, i]) => i?.method === "PUT")[1]![1]!.body))).toEqual({ value: null });
    expect(ask).toHaveBeenCalledTimes(1);
    expect(setItem.mock.calls.some((c) => String(c[1]).includes("s3cret"))).toBe(false);
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain("s3cret");
  });

  it("403 shows the owner-only message and forgets the token", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_u: string, init?: RequestInit) => (init?.method === "PUT" ? json(403, { detail: "bad token" }) : json(200, { overrides: {} }))));
    const ask = vi.spyOn(window, "prompt").mockReturnValue("wrong");
    mount();
    const sw = screen.getByRole("switch", { name: "Toggle ui.system-flags-tab" });
    await userEvent.click(sw);
    expect(await screen.findByRole("alert")).toHaveTextContent("only the owner can change flags (token from keychain item kb-flags-owner)".replace(/^o/, "O"));
    expect(screen.getByRole("alert")).toHaveTextContent("bad token");
    expect(sw).toHaveAttribute("aria-checked", "false");
    await userEvent.click(sw);
    expect(ask).toHaveBeenCalledTimes(2);
  });

  it("public is read-only: no switches, no fetch", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    mount("public");
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    expect(screen.getAllByText("read-only").length).toBeGreaterThan(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
