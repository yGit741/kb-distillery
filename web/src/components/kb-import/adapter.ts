/**
 * How the "Add knowledge base" dialog talks to whoever receives a bundle. The dialog knows nothing of transport: the
 * local app imports at once (localAdapter.ts); a deployed site can queue the bundle for the owner's Mac instead and
 * answer `received`. A build with no adapter (see useImportAdapter) simply does not offer the dialog.
 */

/** Where the bundle comes from: a zipped folder (the browser zips a dropped folder), or a git URL[#ref]. `id` is optional. */
export type ImportSource = ({ kind: "zip"; file: File } | { kind: "git"; url: string }) & { id?: string };

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
}
