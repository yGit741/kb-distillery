import "katex/dist/katex.min.css";
import { Link } from "@tanstack/react-router";
import type { Link as MdLink, Root, Text } from "mdast";
import { useMemo, useRef, type ComponentProps, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { useFlag } from "@/flags/useFlag";
import { cn } from "@/lib/utils";

/** `[[slug]]` or `[[slug|label]]` (the wikilinks left in a page's `## My notes`); the link is marked with this scheme so the renderer can route it. */
const WIKILINK = /\[\[([^\[\]|\n]+?)(?:\|([^\[\]\n]+?))?\]\]/g;
const SCHEME = "kbwiki:";
/** An unsure-formula mark `[!](mark:<sha12>/p0188/3)` (parse transcripts and digests): `!` one voice decided, `!!` unsettled. */
const DOUBT = "mark:";
const DOUBT_REF = /^[0-9a-f]{12}\/p\d{4}\/\d+$/;
/** A figure of a transcribed PDF `![Figure 3.1](figure:<sha12>/p0073/1)`: the PNG cut from the page, served by the API. */
const FIGURE = "figure:";
const FIGURE_REF = /^([0-9a-f]{12})\/(p\d{4})\/(\d+)$/;

/** The API url of a figure ref, or null when `src` is not one. */
export function figureUrl(src: string): string | null {
  if (!src.startsWith(FIGURE)) return null;
  const m = FIGURE_REF.exec(src.slice(FIGURE.length));
  return m ? `/api/figures/${m[1]}/${m[2]}/${m[3]}` : null;
}
/** A page link `slug.md` or `slug.md#heading` (flat, no folder or scheme): `[Title](slug.md)` is how pages link. */
const PAGE_HREF = /^([^/:#?]+)\.md(#.*)?$/;

type Node = Root["children"][number];

/** Remark plugin: page links `[Title](slug.md)` and [[wikilinks]] both become a page route. */
export function remarkWikilinks() {
  return (tree: Root) => {
    const walk = (parent: { children: Node[] }) => {
      const out: Node[] = [];
      for (const child of parent.children) {
        if (child.type === "text") {
          out.push(...splitText(child));
        } else {
          if (child.type === "link") {
            const m = PAGE_HREF.exec(child.url);
            if (m) child.url = SCHEME + encodeURIComponent(safeDecode(m[1]!));
          }
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

/** Remark plugin: a paragraph holding only a doubt mark right after a display formula becomes that formula's tag
 * (`div.kb-doubt-display` > math + `p.kb-doubt-tag`), so the mark sits at the right of the equation, not on its own line. */
export function remarkDoubtTag() {
  const isTag = (n: Node | undefined): boolean => {
    if (n?.type !== "paragraph") return false;
    const kids = n.children.filter((c) => !(c.type === "text" && !c.value.trim()));
    return kids.length === 1 && kids[0]!.type === "link" && kids[0]!.url.startsWith(DOUBT);
  };
  return (tree: Root) => {
    const walk = (parent: { children: Node[] }) => {
      const out: Node[] = [];
      for (let i = 0; i < parent.children.length; i++) {
        const child = parent.children[i]!;
        const next = parent.children[i + 1];
        if (child.type === "math" && isTag(next)) {
          (next as { data?: object }).data = { hProperties: { className: ["kb-doubt-tag"] } };
          out.push({
            type: "doubtDisplay",
            data: { hName: "div", hProperties: { className: ["kb-doubt-display"] } },
            children: [child, next],
          } as unknown as Node);
          i++;
          continue;
        }
        if ("children" in child && child.type !== "paragraph") walk(child as { children: Node[] });
        out.push(child);
      }
      parent.children = out;
    };
    walk(tree);
  };
}

/** `\tag{N}` numbers a display equation; KaTeX refuses it in inline maths (a numbered equation quoted inside a sentence).
 * There it becomes ` \qquad(N)`, the number the reader would see. */
export function inlineTag(tex: string): string {
  return tex.replace(/\\tag\*?\{([^{}]*)\}/g, "\\qquad($1)");
}

/** Remark plugin: `inlineTag` on every inline formula (value and the text node mdast-util-math already made from it). */
export function remarkInlineTag() {
  type MathNode = { type: string; value?: string; children?: MathNode[]; data?: { hChildren?: { type: string; value: string }[] } };
  return (tree: Root) => {
    const walk = (n: MathNode) => {
      if (n.type === "inlineMath" && typeof n.value === "string") {
        n.value = inlineTag(n.value);
        for (const c of n.data?.hChildren ?? []) if (c.type === "text") c.value = inlineTag(c.value);
        return;
      }
      for (const c of n.children ?? []) walk(c);
    };
    walk(tree as unknown as MathNode);
  };
}

const safeDecode = (s: string): string => {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
};

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
  if (url.startsWith(DOUBT) && DOUBT_REF.test(url.slice(DOUBT.length))) return url;
  if (url.startsWith(FIGURE) && FIGURE_REF.test(url.slice(FIGURE.length))) return url;
  if (/^(https?:|mailto:|#|\/|\.\.?\/)/i.test(url) || !/^[a-z][a-z0-9+.-]*:/i.test(url)) return url;
  return "";
}

type RemarkPlugin = NonNullable<ComponentProps<typeof ReactMarkdown>["remarkPlugins"]>[number];

export interface MarkdownProps {
  children: string;
  className?: string;
  /** Maps a page link's slug (`[Title](slug.md)`, or a [[wikilink]]) to the page that should be linked (aliases, renames); return null if there is none. */
  resolveSlug?: (slug: string) => string | null | undefined;
  /** Rewrites relative image/link targets (e.g. vault assets). */
  transformUrl?: (url: string) => string;
  /** Search params every page link carries (`{ kb }` keeps a read-only page's links in its knowledge base). */
  linkSearch?: Record<string, string>;
  /** Numbered citations (flag show-thinking): a page link whose slug has a number gets it as a small superscript, and
   * hovering the link or the number reports the slug; `hot` is the slug to highlight (hovered here or on the graph). */
  cite?: CiteHooks;
  /** Numbered source markers (pages, Footer variant): a remark plugin that adds `sup[data-source-mark=n]` nodes, and how to draw number `n`. */
  marks?: { plugin: RemarkPlugin; render: (n: number) => ReactNode };
  /** Unsure-formula marks (flag parsed-pdf): how to draw the mark `ref` (`<sha12>/p0188/3`) of `level`. Without it, or with
   * the flag off, a mark is plain small text. */
  doubt?: { render: (ref: string, level: "!" | "!!") => ReactNode };
}

export interface CiteHooks {
  numberOf: (slug: string) => number | undefined;
  hot?: string | null;
  onHot?: (slug: string | null) => void;
}

/**
 * The ONE Markdown renderer: GFM, KaTeX ($…$ and $$…$$), light code highlighting and page links (`[Title](slug.md)`, plus the [[slug]] wikilinks of My notes)
 * to /pages/<slug>. Raw HTML in the source is not rendered (react-markdown escapes it), so there is
 * nothing to sanitise and no dangerouslySetInnerHTML.
 */
export function Markdown({ children, className, resolveSlug, transformUrl, linkSearch, cite: citeProp, marks, doubt }: MarkdownProps) {
  const doubtOn = useFlag("parsed-pdf");
  const doubtRef = useRef(doubtOn ? doubt : undefined);
  doubtRef.current = doubtOn ? doubt : undefined;
  const marksRef = useRef(marks);
  marksRef.current = marks;
  // read at render through a ref, so a new hooks object (a hover) never rebuilds the components and remounts the links
  const citeRef = useRef(citeProp);
  citeRef.current = citeProp;
  const components = useMemo<ComponentProps<typeof ReactMarkdown>["components"]>(
    () => ({
      a({ href, children: kids, node: _node, ...rest }) {
        if (href?.startsWith(DOUBT)) {
          const level = String(Array.isArray(kids) ? kids.join("") : kids) === "!!" ? "!!" : "!";
          const draw = doubtRef.current;
          if (draw) return <>{draw.render(href.slice(DOUBT.length), level)}</>;
          return (
            <span className="ml-0.5 align-super text-[10px] font-semibold text-muted-foreground" data-doubt={level}>
              {level}
            </span>
          );
        }
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
          const link = (
            <Link to={`/pages/${encodeURIComponent(resolved)}` as "/"} search={(linkSearch ?? {}) as never} className="wikilink">
              {kids}
            </Link>
          );
          const cite = citeRef.current;
          const n = cite?.numberOf(raw);
          if (n === undefined) return link;
          const hot = cite?.hot === raw;
          const hover = { onMouseEnter: () => citeRef.current?.onHot?.(raw), onMouseLeave: () => citeRef.current?.onHot?.(null) };
          return (
            <span data-cite={raw} data-hot={hot ? "" : undefined} className={cn("rounded-sm", hot && "bg-secondary outline outline-1 outline-border")} {...hover}>
              {link}
              <sup className="ml-px cursor-default px-0.5 text-[10px] font-semibold text-foreground" aria-label={`citation ${n}`}>
                {n}
              </sup>
            </span>
          );
        }
        const external = !!href && /^https?:/i.test(href);
        return (
          <a href={transformUrl && href ? transformUrl(href) : href} {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})} {...rest}>
            {kids}
          </a>
        );
      },
      sup({ node: _node, children: kids, ...rest }) {
        const n = (rest as Record<string, unknown>)["data-source-mark"];
        if (n !== undefined && marksRef.current) return <>{marksRef.current.render(Number(n))}</>;
        return <sup {...rest}>{kids}</sup>;
      },
      table({ node: _node, children: kids }) {
        return (
          <div className="overflow-x-auto">
            <table>{kids}</table>
          </div>
        );
      },
      img({ src, alt, node: _node }) {
        const fig = typeof src === "string" ? figureUrl(src) : null;
        if (fig) return <img src={fig} alt={alt ?? "Figure"} loading="lazy" className="kb-figure" />;
        const url = typeof src === "string" ? (transformUrl ? transformUrl(src) : src) : undefined;
        return <img src={url} alt={alt ?? ""} loading="lazy" />;
      },
    }),
    [resolveSlug, transformUrl, linkSearch],
  );
  const plugin = marks?.plugin;
  const remarkPlugins = useMemo(() => [remarkGfm, remarkMath, remarkInlineTag, remarkWikilinks, remarkDoubtTag, ...(plugin ? [plugin] : [])], [plugin]);
  return (
    <div className={cn("kb-prose", className)}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins}
        rehypePlugins={[rehypeKatex, [rehypeHighlight, { detect: false, ignoreMissing: true }]]}
        urlTransform={urlTransform}
        components={components}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}

const unwrap = { p: ({ children }: { children?: ReactNode }) => <>{children}</> };

/** A short line of text (a page title) with its `$...$` maths typeset, through the same remark-math + KaTeX path as a
 * page body; text without a `$` is returned as it is. */
export function MathText({ text }: { text: string }) {
  if (!text.includes("$")) return <>{text}</>;
  return (
    <ReactMarkdown remarkPlugins={[remarkMath, remarkInlineTag]} rehypePlugins={[rehypeKatex]} components={unwrap}>
      {text}
    </ReactMarkdown>
  );
}

/** A title as plain text (the browser tab): `$W_K^\\top$` reads `W_K^top`. */
export function plainTitle(text: string): string {
  return text.replace(/\$([^$]+)\$/g, (_m, tex: string) => tex.replace(/\\([a-zA-Z]+)/g, "$1"));
}
