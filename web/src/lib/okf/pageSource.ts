import yaml from "js-yaml";

/** A page file's text rebuilt from what the share blob keeps of it: the frontmatter fields and the body. */
export function sourceOf(frontmatter: Record<string, unknown>, markdown: string): string {
  if (!Object.keys(frontmatter).length) return markdown;
  return `---\n${yaml.dump(frontmatter, { lineWidth: -1 })}---\n\n${markdown}`;
}
