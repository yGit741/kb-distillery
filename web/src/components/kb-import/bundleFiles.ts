import { zipStore, type ZipEntry } from "./zip";

/** More than this and the server refuses the upload anyway (64 MB); say so before reading it all. */
export const MAX_BUNDLE_BYTES = 64 * 1024 * 1024;

const SKIP = new Set([".git", ".DS_Store", "__MACOSX", "node_modules"]);

export class BundleSourceError extends Error {}

export interface FolderFile {
  /** Path inside the folder, forward slashes, no leading folder name. */
  path: string;
  file: File;
}

function readBytes(file: Blob): Promise<Uint8Array> {
  if (typeof file.arrayBuffer === "function") return file.arrayBuffer().then((b) => new Uint8Array(b));
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(new Uint8Array(r.result as ArrayBuffer));
    r.onerror = () => reject(r.error);
    r.readAsArrayBuffer(file);
  });
}

/** One zip named `<folder>.zip` holding the files under `<folder>/` (what zipping a folder produces). */
export async function zipFolder(name: string, files: readonly FolderFile[]): Promise<File> {
  const kept = files.filter((f) => !f.path.split("/").some((seg) => SKIP.has(seg)));
  if (!kept.length) throw new BundleSourceError("That folder has no files to import.");
  if (kept.reduce((n, f) => n + f.file.size, 0) > MAX_BUNDLE_BYTES) throw new BundleSourceError("That folder is over 64 MB; import a smaller bundle.");
  const entries: ZipEntry[] = [];
  for (const f of kept) entries.push({ path: `${name}/${f.path}`, data: await readBytes(f.file) });
  return new File([zipStore(entries)], `${name}.zip`, { type: "application/zip" });
}

const isZip = (f: File) => /\.zip$/i.test(f.name);

function checkZip(f: File): File {
  if (!isZip(f)) throw new BundleSourceError("Drop a folder or a .zip file.");
  if (f.size > MAX_BUNDLE_BYTES) throw new BundleSourceError("That zip is over 64 MB; import a smaller bundle.");
  return f;
}

/** Files picked with the folder chooser (`webkitdirectory`; copy them out of the input's FileList before clearing it): every `webkitRelativePath` starts with the folder's name. */
export async function bundleFromFolderInput(list: readonly File[]): Promise<File> {
  const name = list[0]?.webkitRelativePath.split("/")[0];
  if (!name) throw new BundleSourceError("That folder has no files to import.");
  return zipFolder(name, list.map((file) => ({ path: file.webkitRelativePath.split("/").slice(1).join("/"), file })));
}

/** Files picked with the file chooser: one .zip. */
export const bundleFromFileInput = (files: readonly File[]): File => {
  if (files.length !== 1) throw new BundleSourceError("Choose one .zip file.");
  return checkZip(files[0]!);
};

const entryFile = (e: FileSystemFileEntry) => new Promise<File>((res, rej) => e.file(res, rej));
const readAll = (dir: FileSystemDirectoryEntry) =>
  new Promise<FileSystemEntry[]>((resolve, reject) => {
    const reader = dir.createReader();
    const all: FileSystemEntry[] = [];
    const next = () => reader.readEntries((batch) => (batch.length ? (all.push(...batch), next()) : resolve(all)), reject);
    next();
  });

async function walk(dir: FileSystemDirectoryEntry, prefix: string, out: FolderFile[]): Promise<void> {
  for (const e of await readAll(dir)) {
    if (SKIP.has(e.name)) continue;
    if (e.isDirectory) await walk(e as FileSystemDirectoryEntry, `${prefix}${e.name}/`, out);
    else out.push({ path: prefix + e.name, file: await entryFile(e as FileSystemFileEntry) });
  }
}

/** What was dropped -> a .zip: a dropped .zip as is, a dropped folder zipped here (webkitGetAsEntry). */
export async function bundleFromDrop(dt: DataTransfer): Promise<File> {
  // the entries must be taken synchronously: the DataTransfer is empty once the event handler yields
  const entries = [...dt.items].filter((i) => i.kind === "file").map((i) => i.webkitGetAsEntry?.() ?? null);
  const plain = [...dt.files];
  if ((entries.length || plain.length) > 1) throw new BundleSourceError("Drop one folder or one .zip file.");
  const entry = entries[0];
  if (entry?.isDirectory) {
    const out: FolderFile[] = [];
    await walk(entry as FileSystemDirectoryEntry, "", out);
    return zipFolder(entry.name, out);
  }
  if (!plain.length) throw new BundleSourceError("Drop a folder or a .zip file.");
  return checkZip(plain[0]!);
}
