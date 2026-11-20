import { describe, expect, it } from "vitest";
import type { GraphModel } from "../types";
import { citedByPage, drillable, evidenceScene, indexArtifacts, permalink, viewScene } from "./model";
import type { ArtifactGraph, ArtifactView } from "./types";

const graph: ArtifactGraph = {
  nodes: [
    { id: "repo:r", type: "Repo", name: "r", repo: "r" },
    { id: "r:a", type: "Folder", name: "a", parent: "repo:r", repo: "r", path: "a" },
    { id: "r:b", type: "Folder", name: "b", parent: "repo:r", repo: "r", path: "b" },
    { id: "r:c", type: "Folder", name: "c", parent: "repo:r", repo: "r", path: "c" },
    { id: "r:a/x.cpp", type: "File", name: "x.cpp", parent: "r:a", repo: "r", path: "a/x.cpp" },
    { id: "r:a/z.cpp", type: "File", name: "z.cpp", parent: "r:a", repo: "r", path: "a/z.cpp" },
    { id: "r:b/y.h", type: "File", name: "y.h", parent: "r:b", repo: "r", path: "b/y.h" },
    { id: "sym:X", type: "Symbol", name: "X", parent: "r:a/x.cpp", repo: "r", path: "a/x.cpp", line: 7 },
  ],
  links: [
    { source: "r:a/x.cpp", target: "r:b/y.h", kind: "includes" },
    { source: "r:a/z.cpp", target: "r:b/y.h", kind: "includes" },
    { source: "r:a/x.cpp", target: "r:a/z.cpp", kind: "includes" },
  ],
  repos: { r: { web: "https://git.example.com/octocat/r/blob/abc/" } },
  cards: { "r-a": { facts: { F00001: ["sym:X"] } } },
  types: { Repo: { mark: "repo" }, Folder: { mark: "ring" }, File: { mark: "dot" }, Symbol: { mark: "dot" } },
  cites: { "page-one": ["F00001"] },
};
const structure: ArtifactView = { id: "structure", name: "Structure", types: ["Repo", "Folder", "File"], relations: ["includes"] };

describe("viewScene", () => {
  const ix = indexArtifacts(graph);

  it("opens inside the only repository and lifts links to the folders", () => {
    const s = viewScene(ix, structure, null);
    expect(s.focus).toBe("repo:r");
    expect(s.model.nodes.map((n) => n.id).sort()).toEqual(["r:a", "r:b"]);
    expect(s.model.links).toEqual([{ source: "r:a", target: "r:b", kind: "related", rel: "includes", count: 2 }]);
    expect(s.hidden).toBe(1);
    expect(s.crumbs.map((c) => c.name)).toEqual(["All", "r"]);
  });

  it("drills into a folder: its files plus the outside folder they reach", () => {
    const s = viewScene(ix, structure, "r:a");
    const ids = s.model.nodes.map((n) => n.id).sort();
    expect(ids).toEqual(["r:a/x.cpp", "r:a/z.cpp", "r:b"]);
    expect(s.model.nodes.find((n) => n.id === "r:b")?.properties["outside"]).toBe("1");
    expect(s.model.links).toHaveLength(3);
  });

  it("steps inside only what holds a type the view draws", () => {
    expect(drillable(ix, structure, "r:a")).toBe(true);
    expect(drillable(ix, structure, "r:a/x.cpp")).toBe(false);
    expect(drillable(ix, { ...structure, nest: "none" }, "r:a")).toBe(false);
  });

  it("draws every linked node at once when the view does not nest", () => {
    const s = viewScene(ix, { ...structure, nest: "none" }, "r:a");
    expect(s.focus).toBeNull();
    expect(s.model.nodes).toHaveLength(3);
  });
});

describe("citations", () => {
  const ix = indexArtifacts(graph);

  it("maps a page's facts to artifacts and every ancestor to the page", () => {
    expect(citedByPage(ix, "page-one")).toEqual({ facts: 1, nodes: ["sym:X"] });
    expect([...(ix.citedBy.get("repo:r") ?? [])]).toEqual(["page-one"]);
  });

  it("draws pages with the files their facts are about", () => {
    const concepts: GraphModel = {
      nodes: [{ id: "page-one", slug: "page-one", title: "One", label: "One", type: "idea", layer: "concept", areas: [], added: "", changed: "", depth: "", maturity: "", inDegree: 0, outDegree: 0, path: "", preview: "", properties: {} }],
      links: [],
      conceptLinks: [],
    };
    const s = evidenceScene(ix, concepts, { types: [{ id: "idea", label: "Idea", layer: "concept" }], defaultVisible: ["idea"], depths: [] });
    expect(s.model.nodes.map((n) => n.id)).toEqual(["page-one", "r:a/x.cpp"]);
    expect(s.model.links[0]).toMatchObject({ source: "page-one", target: "r:a/x.cpp", rel: "cites" });
  });

  it("links an artifact to its line at its source host", () => {
    expect(permalink(graph, ix.byId.get("sym:X"))).toBe("https://git.example.com/octocat/r/blob/abc/a/x.cpp#L7");
  });
});
