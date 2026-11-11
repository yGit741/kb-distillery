import type { DataSource } from "@/api";
import type { KbImportRequest } from "@/api/types";
import type { ImportAdapter, ImportSource, LibraryInfo } from "./adapter";

const request = (s: ImportSource): KbImportRequest =>
  s.kind === "zip" ? { file: s.file, id: s.id || undefined }
  : s.kind === "path" ? { path: s.path, id: s.id || undefined }
  : { gitUrl: s.url, id: s.id || undefined };

/** The local app: the server validates and imports into the bases dir right away. */
export function createLocalImportAdapter(ds: DataSource): ImportAdapter {
  return {
    validate: async (source) => {
      const p = await ds.previewKbImport(request(source));
      return { id: p.id, name: p.name, pages: p.pages, source: p.source, errors: p.errors, warnings: p.warnings };
    },
    submit: async (source) => {
      const r = await ds.importKb(request(source));
      return { state: "imported", id: r.id, name: r.name, pages: r.pages };
    },
    library: {
      get: () => ds.getKbLibrary() as Promise<LibraryInfo>,
      set: (path) => ds.setKbLibrary(path) as Promise<LibraryInfo>,
    },
  };
}
