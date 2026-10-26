/**
 * Obsidian-style live preview for CodeMirror 6: Markdown renders as a page, and the syntax marks
 * (#, **, `, ~~, [[ ]]) reappear only on the line the cursor is on. The buffer stays the raw file —
 * decorations change how text LOOKS, never what is saved.
 */
import { autocompletion, type CompletionContext, type CompletionResult } from "@codemirror/autocomplete";
import { markdown, markdownLanguage } from "@codemirror/lang-markdown";
import { HighlightStyle, syntaxHighlighting, syntaxTree } from "@codemirror/language";
import { RangeSetBuilder, type Extension } from "@codemirror/state";
import { Decoration, EditorView, ViewPlugin, type DecorationSet, type ViewUpdate } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";

/** Colours and type come from the app tokens so light/dark both work; no hex here. */
const theme = EditorView.theme({
  "&": { backgroundColor: "transparent", fontSize: "15px" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": { fontFamily: "inherit" }, // prose, not code — CM defaults to monospace here
  ".cm-content": { fontFamily: "inherit", lineHeight: "1.7", caretColor: "var(--primary)", padding: "0" },
  ".cm-line": { padding: "0" },
  ".cm-cursor": { borderLeftColor: "var(--primary)" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": { backgroundColor: "color-mix(in oklab, var(--primary) 18%, transparent)" },
  ".cm-placeholder": { color: "var(--muted-foreground)" },
  ".cm-tooltip": { backgroundColor: "var(--popover)", color: "var(--popover-foreground)", border: "1px solid var(--border)", borderRadius: "8px" },
  ".cm-tooltip.cm-tooltip-autocomplete > ul > li[aria-selected]": { backgroundColor: "var(--accent)", color: "var(--accent-foreground)" },
});

const highlight = HighlightStyle.define([
  { tag: t.heading1, fontSize: "1.5em", fontWeight: "650" },
  { tag: t.heading2, fontSize: "1.25em", fontWeight: "650" },
  { tag: t.heading3, fontSize: "1.1em", fontWeight: "600" },
  { tag: [t.heading4, t.heading5, t.heading6], fontWeight: "600" },
  { tag: t.emphasis, fontStyle: "italic" },
  { tag: t.strong, fontWeight: "650" },
  { tag: t.strikethrough, textDecoration: "line-through", color: "var(--muted-foreground)" },
  { tag: t.monospace, fontFamily: "ui-monospace, monospace", fontSize: "0.9em" },
  { tag: t.quote, color: "var(--muted-foreground)", fontStyle: "italic" },
  { tag: t.link, color: "var(--primary)" },
  { tag: t.url, color: "var(--muted-foreground)" },
  { tag: t.processingInstruction, color: "var(--muted-foreground)" }, // the marks themselves, when shown
  { tag: t.contentSeparator, color: "var(--muted-foreground)" },
]);

/** Syntax-mark node names that disappear off the active line(s). */
const MARKS = new Set(["HeaderMark", "EmphasisMark", "CodeMark", "StrikethroughMark"]);
const WIKI = /\[\[([^\][\n]+)\]\]/g;

function activeLines(view: EditorView): Set<number> {
  const lines = new Set<number>();
  for (const r of view.state.selection.ranges) {
    const from = view.state.doc.lineAt(r.from).number;
    const to = view.state.doc.lineAt(r.to).number;
    for (let n = from; n <= to; n++) lines.add(n);
  }
  return lines;
}

function buildHide(view: EditorView): DecorationSet {
  const active = activeLines(view);
  const hidden: { from: number; to: number }[] = [];
  const push = (from: number, to: number) => {
    if (!active.has(view.state.doc.lineAt(from).number)) hidden.push({ from, to });
  };
  for (const { from, to } of view.visibleRanges) {
    syntaxTree(view.state).iterate({
      from,
      to,
      enter(node) {
        if (!MARKS.has(node.name)) return;
        // keep list bullets visible; hide a HeaderMark together with its trailing space
        const end = node.name === "HeaderMark" && view.state.sliceDoc(node.to, node.to + 1) === " " ? node.to + 1 : node.to;
        push(node.from, end);
      },
    });
    // [[wikilink]] brackets (not part of the Markdown grammar): style the name, hide the brackets
    const text = view.state.sliceDoc(from, to);
    for (const m of text.matchAll(WIKI)) {
      const s = from + (m.index ?? 0);
      push(s, s + 2);
      push(s + m[0].length - 2, s + m[0].length);
    }
  }
  hidden.sort((a, b) => a.from - b.from || a.to - b.to);
  const builder = new RangeSetBuilder<Decoration>();
  let last = -1;
  for (const h of hidden) {
    if (h.from < last) continue;
    builder.add(h.from, h.to, Decoration.replace({}));
    last = h.to;
  }
  return builder.finish();
}

function buildWikiStyle(view: EditorView): DecorationSet {
  const builder = new RangeSetBuilder<Decoration>();
  for (const { from, to } of view.visibleRanges) {
    const text = view.state.sliceDoc(from, to);
    for (const m of text.matchAll(WIKI)) {
      const s = from + (m.index ?? 0);
      builder.add(s, s + m[0].length, Decoration.mark({ class: "cm-wikilink" }));
    }
  }
  return builder.finish();
}

const wikiTheme = EditorView.baseTheme({
  ".cm-wikilink": { color: "var(--primary)", borderRadius: "3px" },
});

const livePlugin = ViewPlugin.fromClass(
  class {
    hide: DecorationSet;
    wiki: DecorationSet;
    constructor(view: EditorView) {
      this.hide = buildHide(view);
      this.wiki = buildWikiStyle(view);
    }
    update(u: ViewUpdate) {
      if (u.docChanged || u.selectionSet || u.viewportChanged) {
        this.hide = buildHide(u.view);
        this.wiki = buildWikiStyle(u.view);
      }
    }
  },
  {
    provide: (p) => [
      EditorView.decorations.of((v) => v.plugin(p)?.wiki ?? Decoration.none),
      EditorView.decorations.of((v) => v.plugin(p)?.hide ?? Decoration.none),
    ],
  },
);

/** `[[` completes against the wiki's slugs (think notes link informally; nothing is enforced). */
function wikiCompletion(slugs: () => readonly string[]): (ctx: CompletionContext) => CompletionResult | null {
  return (ctx) => {
    const m = ctx.matchBefore(/\[\[([\w-]*)$/);
    if (!m) return null;
    return {
      from: m.from + 2,
      options: slugs().map((s) => ({ label: s, apply: `${s}]]` })),
      validFor: /^[\w-]*$/,
    };
  };
}

export function thinkEditorExtensions(slugs: () => readonly string[]): Extension {
  return [
    markdown({ base: markdownLanguage }),
    syntaxHighlighting(highlight),
    theme,
    wikiTheme,
    livePlugin,
    EditorView.lineWrapping,
    autocompletion({ override: [wikiCompletion(slugs)], icons: false }),
  ];
}
