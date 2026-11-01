import type { PipelineSnapshot } from "@/api/types";

const item = (o: Record<string, unknown>) => ({
  collections: [], companion_of: "", status: "source", ingestion: "cataloged", digestion: "digested", depth: "",
  slug: "", ext: ".pdf", size_kb: 10, age_days: 3, last_op: "", last_op_at: "", url: "", failure: "", next: "", ...o,
});

export const snapshot: PipelineSnapshot = {
  generated_at: "2026-10-24T08:00:00Z",
  coherence: [], counts: {}, inbox: [], recent: [
    { ts: "2026-10-23T09:00:00Z", path: "raw/inbox/a.pdf", dest: "raw/printed-docs/2020-a.pdf", collection: "course-x" },
  ],
  items: [
    item({ path: "raw/printed-docs/2020-easy.pdf", name: "2020-easy.pdf", kind: "printed-docs", unit: "raw/printed-docs/2020-easy.pdf", depth: "easy", slug: "paper-easy", collections: ["course-x"], last_op: "digest", last_op_at: "2026-10-20T10:00:00Z" }),
    item({ path: "raw/printed-docs/2021-deep.pdf", name: "2021-deep.pdf", kind: "printed-docs", unit: "raw/printed-docs/2021-deep.pdf", depth: "deep", slug: "paper-deep", last_op: "digest", last_op_at: "2026-09-02T10:00:00Z" }),
    item({ path: "raw/printed-docs/2022-listed.pdf", name: "2022-listed.pdf", kind: "printed-docs", unit: "raw/printed-docs/2022-listed.pdf", digestion: "not digested", slug: "paper-listed", collections: ["course-x"] }),
    item({ path: "raw/web-clips/queued.md", name: "queued.md", kind: "web-clips", unit: "raw/web-clips/queued.md", digestion: "not digested", status: "queued", ext: ".md" }),
    item({ path: "raw/inbox/new.pdf", name: "new.pdf", kind: "inbox", unit: "raw/inbox/new.pdf", ingestion: "inbox", digestion: "", status: "queued", next: "python3 -m kb_distillery.ingest catalog raw/inbox/new.pdf" }),
    item({ path: "raw/emails/t/thread.md", name: "thread.md", kind: "emails", unit: "raw/emails/t", digestion: "not digested", status: "queued", ext: ".md" }),
    item({ path: "raw/emails/t/pic.png", name: "pic.png", kind: "emails", unit: "raw/emails/t", companion_of: "raw/emails/t/thread.md", digestion: "not digested", status: "asset", ext: ".png" }),
  ],
  titles: { "course-x": "Course X" },
  failures: [{ path: "raw/inbox/bad.pdf", reason: "arXiv did not answer" }],
  summary: { queued_units: 3, queued_mb: 0.1 },
};
