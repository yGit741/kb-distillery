import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { cardNode } from "@/features/pages/lib";
import { NodeMarkG, NodeSwatch } from "./NodeMarkSvg";
import { GEOMETRY, GLYPH_SVG, markOf } from "./spec";

const TYPES = ["paper", "ai-chat", "lecture", "idea", "topic", "question", "person", "course"];

describe("NodeMarkG / NodeSwatch (SVG nodes)", () => {
  it("draws every type with its mark", () => {
    for (const t of TYPES) {
      const { container } = render(<NodeSwatch type={t} color="#123456" />);
      expect(container.querySelector("svg")?.getAttribute("data-swatch"), t).toBe(markOf(t));
      expect(container.querySelector("[data-mark]")?.getAttribute("data-mark"), t).toBe(markOf(t));
    }
  });

  it("puts a source's glyph inside its dot, in the shared path", () => {
    const { container } = render(
      <svg>
        <NodeMarkG type="paper" x={10} y={10} r={10} color="#123456" glyph />
      </svg>,
    );
    expect(container.querySelector("path")?.getAttribute("d")).toBe(GLYPH_SVG.paper.d);
    const { container: none } = render(
      <svg>
        <NodeMarkG type="paper" x={10} y={10} r={10} color="#123456" />
      </svg>,
    );
    expect(none.querySelector("path")).toBeNull();
  });

  it("uses the canvas geometry", () => {
    const { container } = render(
      <svg>
        <NodeMarkG type="course" x={0} y={0} r={10} color="#000" />
      </svg>,
    );
    const rs = [...container.querySelectorAll("circle")].map((c) => Number(c.getAttribute("r")));
    expect(rs).toEqual([10 * GEOMETRY.collectionOuter, 10]);
  });
});

describe("cardNode", () => {
  it("turns a page card into a graph node with its layer", () => {
    const n = cardNode({ id: "p", title: "P", type: "paper", status: "", depth: "full", areas: ["a"], preview: "", words: 1 } as never);
    expect(n).toMatchObject({ id: "p", type: "paper", layer: "source", areas: ["a"], depth: "full" });
    expect(cardNode({ id: "i", title: "", type: "idea", status: "", depth: "", areas: [], preview: "", words: 0 } as never).layer).toBe("concept");
  });
});
