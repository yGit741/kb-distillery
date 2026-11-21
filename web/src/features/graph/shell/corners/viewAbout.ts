import type { EmbeddingReport } from "@/api";
import type { ArtifactView } from "../../artifacts/types";
import type { ArtifactInfo } from "../../artifacts/store";

/**
 * Flag graph.artifacts: what the "?" on a view's card says. `what` is the view in one line; `based` lists, row by row, the
 * data the view is drawn from. Every number is counted from the data on screen, every sentence restates what the code
 * that draws the view does: nothing here is a guess.
 */
export interface ViewAbout {
  what: string;
  based: { label: string; text: string }[];
}

const num = (n: number) => n.toLocaleString("en-US");
const plural = (n: number, one: string, many = `${one}s`) => `${num(n)} ${n === 1 ? one : many}`;

/** A view a template declares on its intermediate layer: the node types and link kinds it draws, counted in the artifact graph. */
export function aboutArtifactView(v: ArtifactView, info: ArtifactInfo | null): ViewAbout {
  const based: ViewAbout["based"] = [];
  based.push({ label: "Nodes", text: info ? `${v.types.map((t) => `${num(info.types[t] ?? 0)} ${t}`).join(" · ")} in the artifact graph` : v.types.join(" · ") });
  const kinds = v.relations ?? [];
  based.push({
    label: "Links",
    text: kinds.length
      ? kinds
          .map((k) => {
            const words = info?.relationWords[k];
            return `${k}${info ? ` (${num(info.relations[k] ?? 0)})` : ""}${words ? `: ${words}` : ""}`;
          })
          .join("; ")
      : "every link between those nodes",
  });
  if (v.color_by) based.push({ label: "Colour", text: `by ${v.color_by}` });
  if (v.size_by) based.push({ label: "Size", text: `by ${v.size_by}` });
  based.push({
    label: "Shown",
    text:
      v.nest === "none"
        ? "every linked node at once"
        : "one level at a time, from the top of the containment tree down. A link between deeper nodes is drawn between the nodes on screen that hold them",
  });
  const from = builtFrom(info, v.builder);
  if (from) based.push({ label: "Built from", text: from });
  return { what: v.hint || v.name, based };
}

function builtFrom(info: ArtifactInfo | null, builder?: string | null): string {
  if (!info) return builder ? `the ${builder} builder` : "";
  const by = [info.generator, builder && `builder ${builder}`].filter(Boolean).join(", ");
  const of = [info.repos ? plural(info.repos, "repository", "repositories") : "", info.project && `project ${info.project}`].filter(Boolean).join(" of ");
  const head = [by, of && `reading ${of}`].filter(Boolean).join(" ");
  return [head || "this knowledge base's artifact graph", info.template && `template ${info.template}`].filter(Boolean).join("; ");
}

/** The Evidence view: the pages that cite a fact, beside the code those facts are about. */
export function aboutEvidence(info: ArtifactInfo | null): ViewAbout {
  const based: ViewAbout["based"] = [
    { label: "Pages", text: info ? `${plural(info.pages, "page")} whose text cites a fact about the code` : "the pages whose text cites a fact about the code" },
    { label: "Facts", text: `${info ? `${plural(info.facts, "fact id")} cited` : "the fact ids cited"}; each fact card says which pieces of code its fact is about` },
    { label: "Links", text: "one from a page to each file its facts are about, and the page links among those pages" },
    { label: "Built from", text: "the wiki text (which fact ids a page cites) and the fact cards of the artifact graph" },
  ];
  return { what: "Pages beside the code their facts cite", based };
}

/** The Citations view: the paper pages joined by the references Semantic Scholar lists. */
export function aboutCitations(o: { papers: number; cites?: number }): ViewAbout {
  return {
    what: "Papers joined by who cites whom",
    based: [
      { label: "Nodes", text: `the paper pages of this knowledge base (${num(o.papers)}); a paper with no citation link stays out while Connected is on` },
      { label: "Links", text: `${o.cites === undefined ? "cites" : `${num(o.cites)} cites`}: paper A lists paper B in its references. Only links between two pages of this knowledge base` },
      { label: "Colour", text: "how deeply each paper was read, from ingest only to deep digest" },
      { label: "Size", text: "the page's inbound links in the wiki (every link to it, not only citations)" },
      { label: "Built from", text: "the reference lists of Semantic Scholar, kept in this knowledge base's citation cache (.cache/citations.json)" },
    ],
  };
}

/** The Semantics view (the meaning map): each page placed by two principal components of its card's vector. */
export function aboutSemantics(r: Pick<EmbeddingReport, "model" | "dim" | "vectors" | "components"> | undefined, axes: readonly [number, number] = [0, 1]): ViewAbout {
  const share = (i: number) => {
    const c = r?.components.find((x) => x.index === i);
    return c ? ` (${(c.variance * 100).toFixed(1)}% of the variance)` : "";
  };
  const based: ViewAbout["based"] = [
    { label: "Position", text: `x is principal component ${axes[0] + 1}${share(axes[0])} of the page vectors, y is component ${axes[1] + 1}${share(axes[1])}` },
  ];
  if (r) based.push({ label: "Vectors", text: `${plural(r.vectors, "page card")} embedded${r.model ? ` with ${r.model}` : ""}, ${num(r.dim)} dimensions each` });
  based.push({ label: "Not used", text: "the links between pages. A page with no vector stands in a column on the right" });
  return { what: "Pages placed by meaning, from the embedding", based };
}
