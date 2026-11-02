import type { PageDetail } from "@/api/types";
import type { ShareBlob } from "./blob";

/** A small vault shaped like the baked blob: page links, headings, tables, labels, a My notes wikilink, a disconnected island. */
const BODIES: Record<string, { title: string; type: string; body: string; links: string[] }> = {
  "tensor-rank": {
    title: "Tensor rank",
    type: "idea",
    body: "# Tensor rank\n\nThe rank of a [CP decomposition](cp-decomposition.md) counts terms.\n\n| a | b |\n|---|---|\n| rank | table row |\n\nSee **[Matrix rank](matrix-rank.md)** and [web](https://example.com/rank).",
    links: ["cp-decomposition", "matrix-rank"],
  },
  "cp-decomposition": {
    title: "CP decomposition",
    type: "idea",
    body: "Canonical polyadic form. Related to [Tensor rank](tensor-rank.md) and [Implicit regularization in matrix factorization](2019-implicit-regularization.md).\n\nRank minimisation is NP-hard.\n\n## My notes\n\nA note about [[tensor-rank]].",
    links: ["tensor-rank", "2019-implicit-regularization"],
  },
  "matrix-rank": {
    title: "Matrix rank",
    type: "idea",
    body: "Linear algebra basics. `rank(A)` equals the dimension of the column space.\n> a quote about rank\n\nSee [Tensor rank](tensor-rank.md).",
    links: ["tensor-rank"],
  },
  "2019-implicit-regularization": {
    title: "Implicit regularization in matrix factorization",
    type: "paper",
    body: "Problem: why does gradient descent find low rank solutions?\n\nMain result: with small init, GD on [factorized](matrix-rank.md) objectives approaches the nuclear norm minimiser.",
    links: ["matrix-rank", "cp-decomposition"],
  },
  "course-learning-theory": {
    title: "Learning theory",
    type: "course",
    body: "# Learning theory\n\nLectures: [PAC learning](lecture-01-pac.md), [VC dimension](lecture-02-vc.md).",
    links: ["lecture-01-pac", "lecture-02-vc"],
  },
  "lecture-01-pac": { title: "PAC learning", type: "lecture", body: "Probably approximately correct. Sample complexity ~ 1/eps.\n", links: ["lecture-02-vc"] },
  "lecture-02-vc": { title: "VC dimension", type: "lecture", body: "Shattering and VC dimension; links back to [PAC learning](lecture-01-pac.md).", links: ["lecture-01-pac", "2019-implicit-regularization"] },
  "island": { title: "Island", type: "idea", body: "Nothing links here, not even a rank mention? rank.", links: [] },
  "no-title-body": { title: "", type: "idea", body: "", links: [] },
};

export function makeFixtureBlob(): ShareBlob {
  const pages: Record<string, PageDetail> = {};
  const links: string[][] = [];
  for (const [slug, p] of Object.entries(BODIES)) {
    for (const t of p.links) links.push([slug, t]);
  }
  links.sort((a, b) => (a[0]! + a[1]!).localeCompare(b[0]! + b[1]!));
  for (const [slug, p] of Object.entries(BODIES)) {
    const backlinks = links.filter((l) => l[1] === slug).map((l) => ({ id: l[0]!, context: `context of ${l[0]} -> ${slug}` }));
    pages[slug] = {
      card: { id: slug, title: p.title, type: p.type, maturity: "seed", depth: "", areas: [], words: p.body.split(/\s+/).length, preview: `preview of ${slug}` },
      path: `wiki/${slug}.md`,
      frontmatter: { type: p.type },
      markdown: p.body,
      backlinks,
      outbound: p.links,
      broken: [],
      suggested: [],
    } as PageDetail;
  }
  const nodes = Object.values(pages).map((p) => ({ id: p.card.id, label: p.card.title, title: p.card.title, type: p.card.type, layer: "concept", maturity: "seed", depth: "", areas: [], inDegree: 0, outDegree: 0, path: "", added: "", changed: "", preview: "", properties: {} }));
  return {
    graph: { generated_at: "2026-01-01T00:00:00Z", etag: "e", node_count: nodes.length, link_count: links.length, nodes, links: links.map(([source, target]) => ({ source: source!, target: target!, kind: "wikilink" })), schema: {}, concept_links: [], facets: { types: [], maturities: [], areas: [] } },
    index: { generated_at: "2026-01-01T00:00:00Z", pages: Object.values(pages).map((p) => p.card), links, wanted: [], wanted_total: 0 },
    pages,
    meta: { kb_version: "1.2.3", content_sha: "0123456789abcdef", viewer_sha: "fedcba9876543210", profile: "public", built_at: "2026-01-01T00:00:00Z" },
  } as ShareBlob;
}

/** A larger deterministic vault (seeded PRNG) for the differential test: many words, many links. */
export function makeRandomBlob(n = 80, seed = 7): ShareBlob {
  let s = seed;
  const rnd = () => ((s = (s * 1664525 + 1013904223) % 4294967296) / 4294967296);
  const words = ["rank", "tensor", "gradient", "descent", "Fourier", "boolean", "entropy", "kernel", "margin", "bound", "init", "norm", "depth", "width", "loss"];
  const slugs = Array.from({ length: n }, (_, i) => `page-${i}`);
  const blob = makeFixtureBlob();
  blob.pages = {};
  const links: string[][] = [];
  const bodies: Record<string, string> = {};
  for (const slug of slugs) {
    const out = new Set<string>();
    for (let k = 0; k < 1 + Math.floor(rnd() * 3); k++) out.add(slugs[Math.floor(rnd() * n)]!);
    out.delete(slug);
    const text = Array.from({ length: 30 + Math.floor(rnd() * 40) }, () => words[Math.floor(rnd() * words.length)]!).join(" ");
    bodies[slug] = `# ${slug}\n\n${text}\n\nSee ${[...out].map((t) => `[${t}](${t}.md)`).join(" and ")}.\n`;
    for (const t of out) links.push([slug, t]);
  }
  for (const slug of slugs) {
    const t = `${words[Math.floor(rnd() * words.length)]} ${words[Math.floor(rnd() * words.length)]} page`;
    blob.pages[slug] = {
      card: { id: slug, title: t, type: "idea", maturity: "seed", depth: "", areas: [], words: 40, preview: `p ${slug}` },
      path: "", frontmatter: {}, markdown: bodies[slug]!,
      backlinks: links.filter((l) => l[1] === slug).map((l) => ({ id: l[0]!, context: `ctx ${l[0]}->${slug}` })),
      outbound: links.filter((l) => l[0] === slug).map((l) => l[1]!), broken: [], suggested: [],
    } as PageDetail;
  }
  blob.index = { ...blob.index, links, pages: Object.values(blob.pages).map((p) => p.card) };
  return blob;
}
