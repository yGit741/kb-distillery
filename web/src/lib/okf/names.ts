// How a source gets its kb id and its shown name: import_kb.default_id and import_kb._display_name in TypeScript. Kept in
// its own module (no YAML) so the site adapter and the Worker's checker share one rule. tests/fixtures/okf-bundles/names.json
// is asserted against both sides.

/** os.path.splitext(name)[0]: drops the last extension, never a leading dot ("bad-notes.zip" -> "bad-notes"). */
export function sourceStem(name: string): string {
  const lead = /^\.*/.exec(name)![0];
  const rest = name.slice(lead.length);
  const dot = rest.lastIndexOf(".");
  return dot > 0 ? lead + rest.slice(0, dot) : name;
}

/** import_kb's default_id: a kb id from a source name. */
export function suggestId(name: string): string {
  const slug = name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40).replace(/^-+|-+$/g, "");
  return slug && /^[a-z0-9]/.test(slug) ? slug : "imported-kb";
}

/** import_kb._display_name(id, None): the kb name an id gives ("bad-notes" -> "Bad notes"). */
export function displayName(id: string): string {
  const s = id.replace(/-/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}
