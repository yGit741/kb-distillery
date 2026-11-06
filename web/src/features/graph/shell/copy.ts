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
  viewEmpty: "Describe the view you want after >, for example colour by area.",
  /** A `>` sentence the rules could not read goes to the older shape path; this says so. */
  sentenceFallback: "Not a sentence I can read here yet, so I asked the graph to shape it.",
  didYouMean: (name: string) => `Did you mean "${name}"?`,
  noSuchPage: (name: string) => `No page is called "${name}".`,
  explainers: {
    replace: "> replaces the current view",
    stack: ">+ adds to the current view",
    remove: ">- removes from the current view",
  },
} as const;
