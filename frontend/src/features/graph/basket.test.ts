import { beforeEach, describe, expect, it } from "vitest";
import type { ScopeRow } from "@/api/types";
import { DRAFTS_KEY, readDrafts } from "@/features/scopes/logic";
import { activeDraft, addRows, byFormat, discard, newTarget, removePath, UNTITLED, useBasket } from "./basket";

const row = (path: string, over: Partial<ScopeRow> = {}): ScopeRow => ({ path, format: path.split("/")[1] ?? "", disposition: "queued", slug: null, page_type: null, digestion: "", collection: [], year: null, ...over });

beforeEach(() => {
  localStorage.clear();
  useBasket.getState().reload();
});

describe("basket", () => {
  it("names a new scope the way the Scopes screen does", () => {
    expect(newTarget("My topic")).toEqual({ slug: "scope-my-topic", title: "My topic", isNew: true });
    expect(newTarget("  !! ")).toBeNull();
  });

  it("adds rows once, makes the draft active and keeps companions out", () => {
    const a = addRows({ active: "", drafts: {} }, UNTITLED, [row("raw/printed-docs/a.pdf"), row("raw/printed-docs/a.pdf"), row("raw/web-clips/f.png", { disposition: "asset:raw/web-clips/c.md" }), row("raw/emails/t/thread.md")]);
    expect(a.added).toBe(2);
    expect(a.store.active).toBe(UNTITLED.slug);
    expect(byFormat(activeDraft(a.store)?.rows ?? []).map(([f, l]) => [f, l.length])).toEqual([["printed-docs", 1], ["emails", 1]]);
    expect(addRows(a.store, UNTITLED, [row("raw/printed-docs/a.pdf")]).added).toBe(0);
  });

  it("removes a row and discards the draft", () => {
    const { store } = addRows({ active: "", drafts: {} }, UNTITLED, [row("raw/printed-docs/a.pdf"), row("raw/printed-docs/b.pdf")]);
    expect(activeDraft(removePath(store, "raw/printed-docs/a.pdf"))?.rows.map((r) => r.path)).toEqual(["raw/printed-docs/b.pdf"]);
    expect(discard(store)).toEqual({ active: "", drafts: {} });
  });

  it("persists in the exact shape the Scopes screen reads", () => {
    useBasket.getState().add({ slug: "scope-x", title: "X", isNew: true }, [row("raw/handwritten/n.pdf")]);
    const raw = JSON.parse(localStorage.getItem(DRAFTS_KEY) ?? "null");
    expect(raw).toEqual({ active: "scope-x", drafts: { "scope-x": { slug: "scope-x", title: "X", isNew: true, rows: [row("raw/handwritten/n.pdf")] } } });
    expect(readDrafts().drafts["scope-x"]?.rows).toHaveLength(1);
    useBasket.getState().discard();
    expect(readDrafts()).toEqual({ active: "", drafts: {} });
  });
});
