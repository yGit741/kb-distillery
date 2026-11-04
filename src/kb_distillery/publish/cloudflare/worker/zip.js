// Minimal zip reader for the inbox (no npm deps; DecompressionStream is built into Workers and Node >= 18).
//
// `readBundle(bytes, limits)` -> Map<path inside the bundle root, Uint8Array>, ready for checkBundle. It mirrors what
// `import_kb` does with the same zip on the Mac, so the site and the Mac agree about the same upload:
//   - the zip-slip checks of `import_kb._safe_extract`: absolute path, drive letter, `..` part, symlink entry -> ZipError
//     (same wording as the Python), plus the Worker's own limits: entries, per-file and total uncompressed size,
//     no encryption, no zip64, only stored/deflate;
//   - `import_kb.find_bundle_root`: `.DS_Store`, `__MACOSX`, `.git` are dropped; a folder holding `wiki/` has that as the
//     bundle root; a single top-level folder is descended into (up to 3 levels).
// A deflate stream is cut off the moment it passes its declared size, so a lying header cannot blow the Worker's memory.

export class ZipError extends Error {}

export const DEFAULT_LIMITS = { maxEntries: 5000, maxFileBytes: 10 * 1024 * 1024, maxTotalBytes: 40 * 1024 * 1024 };
const IGNORED = new Set([".DS_Store", "__MACOSX", ".git"]);
const WIKI = "wiki";
const EOCD = 0x06054b50, CENTRAL = 0x02014b50, LOCAL = 0x04034b50;

function u16(v, o) { return v.getUint16(o, true); }
function u32(v, o) { return v.getUint32(o, true); }

function findEocd(view) {
  const floor = Math.max(0, view.byteLength - 22 - 0xffff);
  for (let i = view.byteLength - 22; i >= floor; i--) if (u32(view, i) === EOCD) return i;
  return -1;
}

// import_kb._safe_extract's path rules; `name` is the entry name as stored.
export function checkEntryName(name) {
  const parts = name.replace(/\\/g, "/").split("/");
  if (name.startsWith("/") || name.startsWith("\\") || /^[A-Za-z]:/.test(name) || parts.includes("..")) {
    throw new ZipError(`unsafe path in zip: '${name}' (absolute or contains ..)`);
  }
  if (name.includes("\0")) throw new ZipError(`unsafe path in zip: '${name}' (NUL byte)`);
  return parts.join("/");
}

async function inflate(data, expected) {
  const reader = new Blob([data]).stream().pipeThrough(new DecompressionStream("deflate-raw")).getReader();
  const chunks = [];
  let total = 0;
  for (;;) {
    let step;
    try { step = await reader.read(); } catch { throw new ZipError("corrupt zip: a compressed entry does not inflate"); }
    if (step.done) break;
    total += step.value.length;
    if (total > expected) {
      await reader.cancel().catch(() => {});
      throw new ZipError("corrupt zip: an entry inflates past its declared size");
    }
    chunks.push(step.value);
  }
  if (total !== expected) throw new ZipError("corrupt zip: an entry inflates to less than its declared size");
  const out = new Uint8Array(total);
  let at = 0;
  for (const c of chunks) { out.set(c, at); at += c.length; }
  return out;
}

/** Central directory -> [{name, method, csize, usize, offset}] after every safety check (nothing inflated yet). */
export function listEntries(bytes, limits = DEFAULT_LIMITS) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const eocd = findEocd(view);
  if (eocd < 0) throw new ZipError("not a readable zip: no end-of-central-directory record");
  const count = u16(view, eocd + 10), cdSize = u32(view, eocd + 12), cdOffset = u32(view, eocd + 16);
  if (count === 0xffff || cdSize === 0xffffffff || cdOffset === 0xffffffff) throw new ZipError("zip64 archives are not supported");
  if (count > limits.maxEntries) throw new ZipError(`the zip has ${count} entries; the limit is ${limits.maxEntries}`);
  if (cdOffset + cdSize > eocd) throw new ZipError("corrupt zip: the central directory is out of range");
  const entries = [];
  const seen = new Set();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let total = 0;
  let p = cdOffset;
  for (let i = 0; i < count; i++) {
    if (p + 46 > bytes.byteLength || u32(view, p) !== CENTRAL) throw new ZipError("corrupt zip: bad central directory entry");
    const flags = u16(view, p + 8), method = u16(view, p + 10);
    const csize = u32(view, p + 20), usize = u32(view, p + 24);
    const nameLen = u16(view, p + 28), extraLen = u16(view, p + 30), commentLen = u16(view, p + 32);
    const mode = u32(view, p + 38) >>> 16, offset = u32(view, p + 42);
    let name;
    try { name = decoder.decode(bytes.subarray(p + 46, p + 46 + nameLen)); } catch { throw new ZipError("corrupt zip: an entry name is not UTF-8"); }
    p += 46 + nameLen + extraLen + commentLen;
    const clean = checkEntryName(name);
    if ((mode & 0o170000) === 0o120000) throw new ZipError(`unsafe entry in zip: '${name}' is a symlink`);
    if (name.endsWith("/")) { entries.push({ name: clean, dir: true }); continue; }   // a folder entry: counts for the bundle root only
    if (flags & 1) throw new ZipError(`encrypted zip entries are not supported: '${name}'`);
    if (method !== 0 && method !== 8) throw new ZipError(`unsupported compression in zip: '${name}'`);
    if (usize > limits.maxFileBytes) throw new ZipError(`'${name}' is ${usize} bytes; the per-file limit is ${limits.maxFileBytes}`);
    total += usize;
    if (total > limits.maxTotalBytes) throw new ZipError(`the zip unpacks to more than ${limits.maxTotalBytes} bytes`);
    if (seen.has(clean)) throw new ZipError(`duplicate entry in zip: '${name}'`);
    seen.add(clean);
    entries.push({ name: clean, method, csize, usize, offset });
  }
  return entries;
}

// import_kb.find_bundle_root on a flat list of paths: returns the prefix ("" or "a/b/") of the bundle root.
export function bundleRoot(paths) {
  let folder = "";
  for (let depth = 0; depth < 3; depth++) {
    const inside = paths.filter((p) => p.startsWith(folder)).map((p) => p.slice(folder.length));
    if (inside.some((p) => p.startsWith(WIKI + "/"))) return folder + WIKI + "/";
    const top = new Set(inside.map((p) => p.split("/")[0]));
    const [only] = top;
    if (top.size === 1 && inside.some((p) => p.startsWith(only + "/"))) { folder += only + "/"; continue; }
    break;
  }
  return folder;
}

/** The zip as the Map `checkBundle` takes: paths relative to the bundle root -> bytes. Throws ZipError. */
export async function readBundle(bytes, limits = DEFAULT_LIMITS) {
  const all = listEntries(bytes, limits).filter((e) => !e.name.split("/").some((part) => IGNORED.has(part)));
  const entries = all.filter((e) => !e.dir);
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const prefix = bundleRoot(all.map((e) => e.name));
  const files = new Map();
  for (const e of entries) {
    if (!e.name.startsWith(prefix)) continue;                            // outside the bundle root: not imported
    if (e.offset + 30 > bytes.byteLength || u32(view, e.offset) !== LOCAL) throw new ZipError("corrupt zip: bad local header");
    const start = e.offset + 30 + u16(view, e.offset + 26) + u16(view, e.offset + 28);
    if (start + e.csize > bytes.byteLength) throw new ZipError("corrupt zip: an entry runs past the end of the file");
    const raw = bytes.subarray(start, start + e.csize);
    let data;
    if (e.method === 0) {
      if (e.csize !== e.usize) throw new ZipError("corrupt zip: a stored entry has two sizes");
      data = raw;
    } else {
      data = await inflate(raw, e.usize);
    }
    files.set(e.name.slice(prefix.length), data);
  }
  return files;
}
