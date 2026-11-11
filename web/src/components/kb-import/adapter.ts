/**
 * How the "Add knowledge base" dialog talks to whoever receives a bundle. The dialog knows nothing of transport: the
 * local app imports at once (localAdapter.ts); a deployed site can queue the bundle for the owner's Mac instead and
 * answer `received`. A build with no adapter (see useImportAdapter) simply does not offer the dialog.
 */

/**
 * Where the bundle comes from: a zipped folder (the browser zips a dropped folder), a git URL[#ref], or a path inside
 * the knowledge library on this computer (local app only). `id` is optional.
 */
export type ImportSource = ({ kind: "zip"; file: File } | { kind: "git"; url: string } | { kind: "path"; path: string }) & { id?: string };

/** An OKF bundle found in the knowledge library. `added`: a knowledge base here was already imported from it. */
export interface LibraryBundle {
  path: string;
  name: string;
  kind: "folder" | "zip";
  added: boolean;
}

/** The knowledge library: a local folder holding bundles; `path` is null until one is set. */
export interface LibraryInfo {
  path: string | null;
  bundles: LibraryBundle[];
}

/** Local app only: the folder the user keeps bundles in. `set(null)` clears it; both answer with a fresh scan. */
export interface LibraryAccess {
  get(): Promise<LibraryInfo>;
  set(path: string | null): Promise<LibraryInfo>;
}

/** What an import of the source would do. Errors block it; warnings do not. */
export interface ImportPreview {
  id: string;
  name: string;
  pages: number;
  /** The zip's file name, or the git URL. */
  source: string;
  errors: string[];
  warnings: string[];
}

/** What happened: imported at once (link to its graph), or handed over and will appear later (`message` says when; `ref` is the receiver's id for it). */
export type ImportOutcome =
  | { state: "imported"; id: string; name: string; pages: number }
  | { state: "received"; message: string; ref?: string };

export interface ImportAdapter {
  validate(source: ImportSource): Promise<ImportPreview>;
  submit(source: ImportSource): Promise<ImportOutcome>;
  /** Absent where there is no library (the menu is then not shown). */
  library?: LibraryAccess;
}
