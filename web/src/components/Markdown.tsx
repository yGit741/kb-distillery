import "katex/dist/katex.min.css";
import { Link } from "@tanstack/react-router";
import type { Link as MdLink, Root, Text } from "mdast";
import { useMemo, type ComponentProps } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { cn } from "@/lib/utils";

/** `[[slug]]` or `[[slug|label]]`; the link is marked with this scheme so the renderer can route it. */
const WIKILINK = /\[\[([^\[\]|\n]+?)(?:\|([^\[\]\n]+?))?\]\]/g;
const SCHEME = "kbwiki:";

type Node = Root["children"][number];

/** Remark plugin: split text nodes around [[wikilinks]] and replace them by link nodes. */
export function remarkWikilinks() {
  return (tree: Root) => {
    const walk = (parent: { children: Node[] }) => {
      const out: Node[] = [];
      for (const child of parent.children) {
        if (child.type === "text") {
          out.push(...splitText(child));
        } else {
          // never rewrite inside code, inline code or existing links
          if ("children" in child && child.type !== "link" && child.type !== "linkReference") {
            walk(child as { children: Node[] });
          }
          out.push(child);
        }
      }
      parent.children = out;
    };
    walk(tree);
  };
}

function splitText(node: Text): Node[] {
  const parts: Node[] = [];
  let last = 0;
  for (const m of node.value.matchAll(WIKILINK)) {
    const slug = m[1]!.trim();
    if (m.index > last) parts.push({ type: "text", value: node.value.slice(last, m.index) });
    const link: MdLink = {
      type: "link",
      url: SCHEME + encodeURIComponent(slug),
      children: [{ type: "text", value: (m[2] ?? m[1]!).trim() }],
    };
    parts.push(link);
    last = m.index + m[0].length;
  }
  if (!parts.length) return [node];
  if (last < node.value.length) parts.push({ type: "text", value: node.value.slice(last) });
  return parts;
}

/** react-markdown's default urlTransform strips unknown schemes; keep ours, drop javascript:/data: etc. */
function urlTransform(url: string): string {
  if (url.startsWith(SCHEME)) return url;
  if (/^(https?:|mailto:|#|\/|\.\.?\/)/i.test(url) || !/^[a-z][a-z0-9+.-]*:/i.test(url)) return url;
  return "";
}

export interface MarkdownProps {
  children: string;
  className?: string;
  /** Maps a [[slug]] to the page that should be linked (aliases, renames); return null if there is none. */
  resolveSlug?: (slug: string) => string | null | undefined;
  /** Rewrites relative image/link targets (e.g. vault assets). */
  transformUrl?: (url: string) => string;
  /** Search params every [[slug]] link carries (`{ kb }` keeps a read-only page's links in its knowledge base). */
  linkSearch?: Record<string, string>;
}

/**
 * The ONE Markdown renderer: GFM, KaTeX ($…$ and $$…$$), light code highlighting and [[slug]] links
 * to /pages/<slug>. Raw HTML in the source is not rendered (react-markdown escapes it), so there is
 * nothing to sanitise and no dangerouslySetInnerHTML.
 */
export function Markdown({ children, className, resolveSlug, transformUrl, linkSearch }: MarkdownProps) {
  const components = useMemo<ComponentProps<typeof ReactMarkdown>["components"]>(
    () => ({
      a({ href, children: kids, node: _node, ...rest }) {
        if (href?.startsWith(SCHEME)) {
          const raw = decodeURIComponent(href.slice(SCHEME.length));
          const resolved = resolveSlug ? resolveSlug(raw) : raw;
          if (!resolved) {
            return (
              <span className="wikilink text-muted-foreground" data-missing="true" title="No such page">
                {kids}
              </span>
            );
          }
          return (
            <Link to={`/pages/${encodeURIComponent(resolved)}` as "/"} search={(linkSearch ?? {}) as never} className="wikilink">
              {kids}
            </Link>
          );
        }
        const external = !!href && /^https?:/i.test(href);
        return (
          <a href={transformUrl && href ? transformUrl(href) : href} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})} {...rest}>
            {kids}
          </a>
        );
      },
      img({ src, alt, node: _node }) {
        const url = typeof src === "string" ? (transformUrl ? transformUrl(src) : src) : undefined;
        return <img src={url} alt={alt ?? ""} loading="lazy" />;
      },
    }),
    [resolveSlug, transformUrl, linkSearch],
  );
  return (
    <div className={cn("kb-prose", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath, remarkWikilinks]}
        rehypePlugins={[rehypeKatex, [rehypeHighlight, { detect: false, ignoreMissing: true }]]}
        urlTransform={urlTransform}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
