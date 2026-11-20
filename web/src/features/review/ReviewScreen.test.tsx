import { createMemoryHistory } from "@tanstack/react-router";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { addMark, MARK_CHARS, MAX_MARKS } from "./marks";
import { queueRows } from "./Queue";
import { layout, pagesFromRows } from "./ReachGraph";
import { SAMPLE_JOBS } from "./sample";
import { editSteps, insertSteps } from "./tours";

const ds = mockDataSource({ getLifecycle: () => new Promise(() => {}), getOps: () => new Promise(() => {}), getHealth: () => new Promise(() => {}) });

const open = () => {
  const router = createAppRouter(createMemoryHistory({ initialEntries: ["/app/review?sample=1"] }));
  render(<App source={ds} router={router} />);
  return router;
};
const progress = () => document.querySelector('[data-tour="review-progress"]')?.textContent ?? "";

describe("Review screen (sample deck)", () => {
  it("opens on the dropped source; A passes it, then A and R decide cards and Z takes one back", () => withFlag("ui.review-deck", true, async () => {
    open();
    expect(await screen.findByText("radar-ghosts.pdf", {}, { timeout: 4000 })).toBeInTheDocument();
    await userEvent.keyboard("a");
    expect(await screen.findByRole("heading", { name: "Radar ghost targets" })).toBeInTheDocument();
    const first = progress();
    await userEvent.keyboard("a");
    await waitFor(() => expect(progress()).not.toBe(first));
    expect(screen.getByRole("button", { name: /Apply 1/ })).toBeInTheDocument();
    await userEvent.keyboard("z");
    expect(await screen.findByRole("heading", { name: "Radar ghost targets" })).toBeInTheDocument();
  }));

  it("E opens the edit line; /merge and /split show under it and / lists them", () => withFlag("ui.review-deck", true, async () => {
    open();
    await screen.findByText("radar-ghosts.pdf", {}, { timeout: 4000 });
    await userEvent.keyboard("a");
    await screen.findByRole("heading", { name: "Radar ghost targets" });
    await userEvent.keyboard("e");
    const line = await screen.findByRole("textbox", { name: /what should change/i });
    await waitFor(() => expect(line).toHaveFocus());
    const commands = screen.getByLabelText("Commands");
    expect(within(commands).getByText("Fold another page in")).toBeInTheDocument();
    expect(within(commands).getByText("Cut this page in two")).toBeInTheDocument();
    await userEvent.type(line, "/");
    const menu = await screen.findByRole("listbox");
    expect(within(menu).getByText("/merge")).toBeInTheDocument();
    expect(within(menu).getByText("/split")).toBeInTheDocument();
  }));

  it("a page picked in the graph goes with the edit as a chip, and leaves with the card", () => withFlag("ui.review-deck", true, async () => {
    open();
    await screen.findByText("radar-ghosts.pdf", {}, { timeout: 4000 });
    await userEvent.keyboard("a");
    await screen.findByRole("heading", { name: "Radar ghost targets" });
    const reach = document.querySelector('[data-tour="review-reach"]') as HTMLElement;
    expect(within(reach).getByText(/^Touches \d+ pages?$/)).toBeInTheDocument();
    await userEvent.click(within(reach).getAllByRole("checkbox")[0]!);
    const chips = await screen.findByRole("list", { name: "Goes with your next edit" });
    expect(within(chips).getAllByRole("listitem")).toHaveLength(1);
    await userEvent.keyboard("a");
    await waitFor(() => expect(screen.queryByRole("list", { name: "Goes with your next edit" })).toBeNull());
  }));

  it("the edit- and insert-knowledge tours run on the sample deck and point at its own anchors", () => {
    expect(editSteps()).toHaveLength(7);
    expect(insertSteps()).toHaveLength(6);
    for (const steps of [editSteps(), insertSteps()]) {
      expect(steps[0]!.go).toBe("/review?sample=1");
      expect(steps.every((s) => s.target?.startsWith('[data-tour="review-'))).toBe(true);
    }
  });
});

describe("review side panels", () => {
  it("queue rows: reading, waiting with its card count, failed, done", () => {
    const rows = queueRows(SAMPLE_JOBS, new Map([["s-ingest", 2]]));
    const by = Object.fromEntries(rows.map((r) => [r.id, r]));
    expect(by["j-run"]).toMatchObject({ group: "running", failed: false });
    expect(by["j-radar"]).toMatchObject({ group: "waiting", cards: 2, name: "radar-ghosts.pdf" });
    expect(by["j-fail"]).toMatchObject({ group: "running", failed: true });
    expect(by["j-old"]!.group).toBe("done");
  });

  it("graph search rows become pages: slugs, kb-prefixed ids and nodes, once, never the card's own page", () => {
    const titles = new Map([["radar", "Radar"], ["camera", "Camera"], ["tracking", "Object tracking"]]);
    const rows = [["radar", "kb:camera"], [{ slug: "tracking" }, "radar"], ["sensor-fusion", 3]];
    expect(pagesFromRows(rows, titles, "camera")).toEqual([{ slug: "radar", title: "Radar" }, { slug: "tracking", title: "Object tracking" }]);
  });

  it("layout: changed links on the inner ring, neighbours outside, found pages beyond, capped", () => {
    const reach = { total: 30, pages: Array.from({ length: 30 }, (_, i) => ({ slug: `p${i}`, title: `P${i}`, rel: (i < 2 ? "added" : i % 2 ? "in" : "out") as "added" | "in" | "out", exists: true })) };
    const { nodes, more } = layout(reach, [{ slug: "p0", title: "P0" }, { slug: "x", title: "X" }]);
    expect(more).toBe(6);
    expect(nodes.filter((n) => n.rel === "found").map((n) => n.slug)).toEqual(["x"]);
    const r = (n: { x: number; y: number }) => Math.round(Math.hypot(n.x, n.y));
    expect(r(nodes.find((n) => n.rel === "added")!)).toBeLessThan(r(nodes.find((n) => n.rel === "in")!));
  });

  it("marks: trimmed, cut to the length limit, no repeats, at most five", () => {
    let m: string[] = [];
    m = addMark(m, "  a passage  ");
    m = addMark(m, "a passage");
    expect(m).toEqual(["a passage"]);
    m = addMark(m, "x".repeat(MARK_CHARS + 50));
    expect(m[1]).toHaveLength(MARK_CHARS);
    for (let i = 0; i < 10; i++) m = addMark(m, `p${i}`);
    expect(m).toHaveLength(MAX_MARKS);
  });
});
