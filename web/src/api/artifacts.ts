/**
 * The artifact layer as `GET /api/artifacts` serves it (and a share build bakes it): a KB's `artifacts/graph.json`,
 * written by a builder (a code toolkit's `export`, say), plus which page cites which fact. Artifacts are never pages:
 * they sit between the concepts and the sources, and pages reach them only through the facts (`F` + 5 hex digits)
 * they cite. Generated: the shapes come from the server models (`kb_distillery.server.models.artifacts`).
 */
import type { components } from "./schema";

type S = components["schemas"];

/** An artifact: `parent` is the containment tree (a folder's file, a file's class) drill-down follows; roots are repositories. */
export type ArtifactNode = S["ArtifactNode"];
/** A relation between two artifacts; `at` = `<repo>:<path>#L<line>`, where the code says so. */
export type ArtifactLink = S["ArtifactLink"];
/** A view the builder declares: which types and relations it draws; `nest` tree (default) drills down, none draws all. */
export type ArtifactView = S["ArtifactView"];
/** A fact card: fact id -> the artifact nodes it is about. */
export type ArtifactCard = S["ArtifactCard"];
export type ArtifactGraph = S["ArtifactGraph"];
