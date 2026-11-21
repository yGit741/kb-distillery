import { afterEach, describe, expect, it } from "vitest";
import { useGraphUi } from "../store";
import { artifactInfo, enterArtifacts, inArtifacts, leaveArtifacts } from "./store";
import type { ArtifactGraph } from "./types";

describe("the artifact layer's switch", () => {
  afterEach(() => leaveArtifacts());

  it("a scene sets the concept settings aside once and gives them back as they were", () => {
    useGraphUi.setState({ shownTypes: new Set(["idea"]), colorBy: "area", story: "map", search: "tensor" });
    enterArtifacts(new Set(["Repo", "Folder"]), "type");
    expect(inArtifacts()).toBe(true);
    expect([...(useGraphUi.getState().shownTypes ?? [])]).toEqual(["Repo", "Folder"]);
    expect(useGraphUi.getState().search).toBe("");
    // a second scene (a drill-in) keeps the first set of settings
    enterArtifacts(new Set(["File"]), "area");
    leaveArtifacts();
    expect(inArtifacts()).toBe(false);
    const ui = useGraphUi.getState();
    expect([...(ui.shownTypes ?? [])]).toEqual(["idea"]);
    expect([ui.colorBy, ui.story, ui.search]).toEqual(["area", "map", "tensor"]);
  });

  it("leaving when no scene is drawn changes nothing", () => {
    useGraphUi.setState({ search: "kept" });
    leaveArtifacts();
    expect(useGraphUi.getState().search).toBe("kept");
  });

  it("counts what the views are drawn from", () => {
    const g: ArtifactGraph = {
      nodes: [
        { id: "a", type: "File", name: "a" },
        { id: "b", type: "File", name: "b" },
      ],
      links: [{ source: "a", target: "b", kind: "imports" }],
      relations: { imports: { description: "file A includes file B" } },
      repos: { r: {} },
      cites: { p: ["F00001", "F00002"], q: ["F00001"] },
    };
    expect(artifactInfo(g, 2)).toMatchObject({ types: { File: 2 }, relations: { imports: 1 }, relationWords: { imports: "file A includes file B" }, repos: 1, pages: 2, facts: 2 });
  });
});
