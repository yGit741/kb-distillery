import { useShellStore } from "../shell/shellStore";
import { FAVORITE_ERROR, useFavorites } from "./store";

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status });

beforeEach(() => {
  useFavorites.setState({ slugs: new Set(), loaded: false });
  useShellStore.setState({ notice: null });
});

describe("favorites store", () => {
  it("loads the set from GET /api/favorites", async () => {
    const f = vi.fn(async () => json({ slugs: ["a", "b"] }));
    await useFavorites.getState().load(undefined, f as never);
    expect(f).toHaveBeenCalledWith("/api/favorites", expect.anything());
    expect([...useFavorites.getState().slugs]).toEqual(["a", "b"]);
    expect(useFavorites.getState().loaded).toBe(true);
    expect(useFavorites.getState().isFavorite("a")).toBe(true);
  });

  it("a failed load leaves it empty and says nothing", async () => {
    await useFavorites.getState().load(undefined, (async () => json({}, 500)) as never);
    expect(useFavorites.getState().slugs.size).toBe(0);
    expect(useFavorites.getState().loaded).toBe(false);
    expect(useShellStore.getState().notice).toBeNull();
  });

  it("toggles at once, then POSTs to add and DELETEs to remove", async () => {
    const calls: [string, string | undefined][] = [];
    const f = vi.fn(async (url: string, init?: RequestInit) => (calls.push([url, init?.method]), json({ ok: true })));
    const p = useFavorites.getState().toggle("a-page", f as never);
    expect(useFavorites.getState().isFavorite("a-page")).toBe(true); // before the server answered
    await p;
    await useFavorites.getState().toggle("a-page", f as never);
    expect(useFavorites.getState().isFavorite("a-page")).toBe(false);
    expect(calls).toEqual([
      ["/api/favorites", "POST"],
      ["/api/favorites/a-page", "DELETE"],
    ]);
    expect(JSON.parse(String(f.mock.calls[0]![1]!.body))).toEqual({ slug: "a-page" });
  });

  it("puts the page back and says so quietly when the server refuses", async () => {
    await useFavorites.getState().toggle("a", (async () => json({}, 500)) as never);
    expect(useFavorites.getState().isFavorite("a")).toBe(false);
    expect(useShellStore.getState().notice?.text).toBe(FAVORITE_ERROR);
    useFavorites.setState({ slugs: new Set(["b"]) });
    await useFavorites.getState().toggle("b", (async () => {
      throw new Error("offline");
    }) as never);
    expect(useFavorites.getState().isFavorite("b")).toBe(true);
  });
});
