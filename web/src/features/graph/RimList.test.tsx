import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { RimList } from "./RimList";
import { useRimList } from "./rimListStore";
import type { GNode } from "./types";

const paper = (id: string, title: string, year: number, depth: string) => ({ id, title, year, depth, type: "paper", layer: "source" }) as unknown as GNode;
const papers = [paper("a", "Attention Is All You Need", 2017, "full"), paper("b", "Chinchilla scaling", 2022, "easy"), paper("c", "Deep sets", 2017, "deep")];
const byId = new Map(papers.map((p) => [p.id, p] as const));
const titles = () => within(screen.getByTestId("rim-list")).getAllByRole("listitem").map((li) => li.textContent?.replace(/\d{4}$/, "").trim());

afterEach(() => act(() => useRimList.getState().close()));

describe("RimList", () => {
  it("lists a clump's papers deepest digest first, and the arrow reverses the order", async () => {
    render(<RimList byId={byId} colorBy="depth" />);
    act(() => useRimList.getState().show("Deep learning", ["a", "b", "c"]));
    expect(titles()).toEqual(["Deep sets", "Attention Is All You Need", "Chinchilla scaling"]);
    await userEvent.click(screen.getByRole("button", { name: /reverse the order/i }));
    expect(titles()).toEqual(["Chinchilla scaling", "Attention Is All You Need", "Deep sets"]);
  });

  it("filters by the search line, on title and year, and says how many of how many", async () => {
    render(<RimList byId={byId} colorBy="depth" />);
    act(() => useRimList.getState().show("Deep learning", ["a", "b", "c"]));
    await userEvent.type(screen.getByRole("textbox", { name: "Search these papers" }), "2017");
    expect(titles()).toEqual(["Deep sets", "Attention Is All You Need"]);
    expect(screen.getByText(/2 of 3 uncited papers/)).toBeInTheDocument();
  });
});
