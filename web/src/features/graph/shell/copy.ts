/** All texts of the search line in one place (flag graph-intent), so the wording is edited here and nowhere else. */
export type LineMode = "search" | "view" | "command";

export const LINE_COPY = {
  placeholder: "Search everything · > change the view · / commands",
  /** One quiet line per mode, shown the first time that mode is used. */
  hints: {
    search: "Type to search pages, or ask a question.",
    view: "Describe how the graph should look: > replaces the view, >+ adds to it, >- removes from it.",
    command: "Type a command name. Press Enter to run the highlighted one.",
  } satisfies Record<LineMode, string>,
  closestHeading: "Closest options",
  /** The last row under the closest options; `text` is what was typed after the slash. */
  searchInstead: (text: string) => `Search for '${text}' instead`,
  viewRow: "Change the view:",
  /** Shown in place of the `>` mode on a shared site, where the view cannot be changed by writing. */
  sentenceUnavailable: "Changing the view is not available here",
  /** The placeholder of the line on a shared site: no `>` segment. */
  placeholderShare: "Search everything · / commands",
  viewEmpty: "Describe the view you want after >, for example colour by area.",
  /** A `>` sentence the rules could not read goes to the model; this says so while it works. */
  asking: "Not a sentence I can read by rules, so I am asking a model.",
  /** Which backend read the sentence; the cost is said when the API answered (the subscription is not charged per call). */
  interpretedBy: (backend: string, usd: number, fromBackend?: string | null) =>
    `Interpreted by ${backend}${backend === "api" ? `, about $${usd < 0.01 ? usd.toFixed(4) : usd.toFixed(2)}` : ""}${fromBackend ? ` (${fromBackend} did not answer)` : ""}.`,
  /** Search result groups, in their fixed order (flag graph-intent). */
  groups: {
    pages: "Pages",
    think: "Think notes",
    sets: "Sets",
    views: "Views",
    commands: "Commands",
    related: "Related by meaning",
    ask: "Actions",
  },
  /** Tier 2 (server full text): the sections under the title groups, in order. */
  textGroups: { page: "Pages: full text", think: "Think notes: full text", chat: "Chats", raw: "Raw files" } as Record<"page" | "think" | "chat" | "raw", string>,
  /** "31 pages mention x": `n` pages whose title, alias or tags contain the words. */
  setRow: (n: number) => `${n} pages mention`,
  /** The small mark on a row that was also a hit in a lower group, by the group it was also found in. */
  alsoMark: { title: "title", text: "text", related: "meaning" } as Record<string, string>,
  alsoTitle: { title: "Also a title match", text: "Also found in the text", related: "Also related by meaning" } as Record<string, string>,
  rowActions: "Actions",
  /** The action menu on a result, a set, the focus or the view. */
  actions: {
    focus: { label: "Focus", hint: "Enter" },
    show: { label: "Show only", hint: "this page" },
    read: { label: "Read", hint: "beside the graph" },
    expand: { label: "Expand", hint: "add its neighbours" },
    favorite: { label: "Favorite", unlabel: "Unfavorite", hint: "keep it close" },
    chat: { label: "Chat", hint: "ask about it" },
    think: { label: "Think", hint: "quick note" },
    export: { label: "Export", hint: "OKF bundle", why: "Needs the graph intent line" },
    highlight: { label: "Highlight", hint: "Enter" },
    readSet: { label: "Read", hint: "one after another" },
    showSet: { label: "Show only", hint: "these pages" },
    addToView: { label: "Add to view", hint: "on top" },
    color: { label: "Color", hint: "by type" },
    chatSet: { label: "Chat about these", hint: "ask about them" },
  },
  /** The `/favorites` list and the places that show favorites. */
  favorites: {
    empty: "No favorites yet. Mark one from a page's menu.",
    heading: "Favorites",
    mark: "Favorite",
    toggle: (on: boolean) => (on ? "Remove from favorites" : "Add to favorites"),
  },
  /** The reader's stepper over a set of pages. */
  reader: { of: (i: number, n: number) => `${i} of ${n}`, prev: "Previous page", next: "Next page", nav: "Pages in this set" },
  /** A layer made by Expand. */
  neighborsOf: (title: string) => `neighbors of ${title}`,
  /** `/views`: recent and pinned views, the kit's ready views, then the gallery. */
  views: {
    command: { label: "Views", hint: "recent, pinned and ready" },
    recent: "Recent",
    pinned: "Pinned",
    ready: "Ready views",
    gallery: "Open gallery\u2026",
    galleryHint: "all views",
    allViews: "All views\u2026",
    cannotRun: "Cannot run on this kb",
    cannotRunSay: (name: string) => `${name} cannot run on this kb.`,
    applied: (name: string) => `Applied ${name}.`,
    added: (name: string) => `Added ${name} to the view.`,
  },
  /** The view gallery: a window of every view, with its filter, cards and anchored-view field. */
  gallery: {
    title: "Views",
    command: { label: "Gallery", hint: "all views" },
    filterLabel: "Filter views",
    filterPlaceholder: "Filter by name or description",
    ready: "Ready views",
    pinned: "Pinned",
    recent: "Recent",
    empty: "No view matches.",
    close: "Close",
    apply: "Apply",
    add: "Add",
    pin: "Pin",
    cannotRun: "Cannot run on this kb.",
    usesFocus: (title: string) => `Uses ${title}`,
    nameLabel: (view: string) => `Page for ${view}`,
    namePlaceholder: "Name a page, then Enter",
    noPage: (name: string) => `No page matches ${name}.`,
    didYouMean: "Did you mean",
    pinned1: (name: string) => `Pinned ${name}.`,
    pinFailed: "Could not pin this view.",
  },
  favoritesCommand: { label: "Favorites", hint: "the pages you marked" },
  exportNone: "Could not read those pages to export.",
  exportFailed: "Could not copy to the clipboard.",
  exported: (n: number) => `Copied ${n} ${n === 1 ? "page" : "pages"} as an OKF bundle.`,
  /** A `>` sentence the rules could not read goes to the older shape path; this says so. */
  sentenceFallback: "Not a sentence I can read here yet, so I asked the graph to shape it.",
  /** The quiet row under the input while a sentence is previewed (flag graph-intent). */
  preview: {
    count: (n: number) => (n === 1 ? "1 node" : `${n} nodes`),
    hint: "Enter applies · Esc cancels · Tab edits",
    edit: "Edit the resolved sentence",
    editLabel: "Resolved sentence",
    editHint: "One line per layer. Enter applies exactly what is written.",
    parseError: (line: number, reason: string) => `Line ${line}: ${reason}`,
  },
  /** The search line as an overlay on the other screens. */
  overlay: {
    label: "Search",
    openGraph: "Open the graph",
    openGraphHint: "the graph screen",
    handOff: "Change the view on the graph:",
    handOffHint: "opens the graph",
    empty: "Type to search pages, / for commands.",
    emptyShare: "Type to search pages.",
  },
  /** Meaning search (flags graph-intent and semantic-search). */
  meaningOff: "meaning search is off",
  focusOneFirst: "Focus one node first",
  /** The last row of the panel: opens the chat with the focus and the shown pages as context. */
  askRow: "Ask about",
  askHint: "opens the chat",
  /** Lines of the chat draft that carry the context. */
  chatContext: {
    focus: "Focus",
    shown: (n: number) => `Shown in the graph (${n})`,
    more: (n: number) => `and ${n} more`,
  },
  didYouMean: (name: string) => `Did you mean "${name}"?`,
  noSuchPage: (name: string) => `No page is called "${name}".`,
  explainers: {
    replace: "> replaces the current view",
    stack: ">+ adds to the current view",
    remove: ">- removes from the current view",
  },
} as const;
