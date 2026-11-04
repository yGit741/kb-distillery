# The graph shell

The graph screen has a calm layout behind the runtime flag `graph-shell`. The app bar and the toolbar are gone. One search line sits at the top, four small controls sit in the corners, and the graph fills the rest. Everything the old bars offered is still there, reached through the line. This guide says where each option went and what you can write in the line.

Turn it on as the owner with `PUT /api/flags/graph-shell` (see the [HTTP API](../reference/http-api.md)), or from the Flags tab of the System screen when that tab is on. With the flag off the graph screen is unchanged.

## What is on the screen

| Place | What it is |
|---|---|
| Top centre | The search line. Click it, press Cmd-K (Ctrl-K elsewhere), or press `/` or Space while nothing is focused. The panel under it shows recent steps and pinned views at rest, pages while you type, commands after a slash. |
| Top left | Pinned views. Pin the graph as it looks now, rename a pin, unpin it, or step back through recent steps. |
| Top right | Think notes: your latest notes, with New and Open full screen. |
| Bottom left | Agent chats: earlier chats, with New and Open full screen. |
| Right edge | The colour legend: dots that open into names. Pressing a name hides that colour. |
| Bottom centre | The page types: one mark per type. Hover to light a type up, click to hide or show it, press the bar to read the names. |

A first visit offers a short tour of these. Replay it from the Tours menu while the graph is open, or open `/graph?tour=graph-shell`.

Pinned views, Think and Agent need the local app. A published snapshot has the search line, the colour legend and the page types only.

## Where the old options went

Open the line, type `/`, then a word of the name to filter the list. The sections are View, Panels, Knowledge bases and Go to.

| Before | Now |
|---|---|
| Toolbar: Labels and views | `/labels and views` opens the left rail (view, labels, colour, size). |
| Toolbar: Filters | `/filters` |
| Toolbar: Layout and sync | `/layout` (force, live sync, reheat, refresh). |
| Toolbar: Shortcuts | `/shortcuts` |
| Toolbar: tools (Ask, selection tools, scope draft, raw files, graph query, citation genealogy) | One command each under Panels, with the same name and key as before. |
| Relations sheet (relation proposals) | `/relation proposals` opens the sheet over the live graph. |
| Scopes sheet | `/scopes` opens the sheet over the live graph. |
| Zoom in, Zoom out, Fit to view | `/zoom in`, `/zoom out`, `/fit`. The keys `+`, `-` and `F` and the mouse wheel still work. |
| Reheat layout | `/reheat` |
| Refresh now | `/refresh` |
| Views bar (named stories) | The View list in the labels and views rail. Your own named views are the pins at top left. |
| Colour by | The colour legend at the right edge shows the current choice. Change it in the labels and views rail, or write `colour by ...` in the line (see below). |
| Knowledge base picker | The database icon at the left of the line opens the list: `Show <name> only` for each knowledge base (needs the `kb-view` flag). |
| Other screens | `/` then a screen name; the System tabs are listed as `System: ...`. |
| Back to Home (when the graph was opened from Home) | `/home`, or the browser's Back button. |

## What you can write in the line

| You type | You get |
|---|---|
| Part of a page name | Matching pages. Enter centres the graph on one (bringing it in if a filter hides it); Shift-Enter reads it in the side reader. |
| `/` and a word | A command list, filtered as you type. |
| A sentence that is not a command | **Ask the agent** sends it to the chat. **Show pages mentioning ...** keeps the pages that mention the words, with their neighbours. |
| A style clause or a Cypher query | **Shape the graph**: see the next section. |

## Shaping the graph in words

Free text becomes a view in two parts: a Cypher selection (which nodes) and a style (how they are drawn). `POST /api/graph/shape` does the work; its request and response are in the [HTTP API](../reference/http-api.md).

Text that starts with `MATCH (` is raw Cypher and runs as written, with no model call. A line that holds only style clauses keeps the current nodes and changes how they are drawn, also with no model call. Anything else goes through the shared LLM tool once, so it is billed on the backend you configured (`$KB_LLM_BACKEND`, default subscription).

Style clauses are separated by `;` or a new line. A later clause of the same kind replaces an earlier one, except `hide`, which accumulates.

| Clause | Takes | Example |
|---|---|---|
| `group by` | a node property (`type`, `layer`, `depth`, `maturity`, `areas`, `year`, `title`, `slug`, `path`), `label` or `edge-kind` | `group by layer` |
| `colour by` (or `color by`) | a node property, `label` or `degree` | `colour by degree` |
| `size by` | `degree` or a node property | `size by degree` |
| `layout` | `force`, `radial`, `grid` or `timeline` | `layout timeline` |
| `hide` | a node label, or an edge kind in capitals; repeatable or comma separated | `hide Paper`, `hide MENTIONS` |
| `label` | the node property shown as the node's text | `label title` |

`hide label Open Problem` and `hide edge MENTIONS` say which kind of name you mean when the spelling could be either.

Examples:

```text
group by type; colour by degree
layout radial; hide MENTIONS
MATCH (p:Paper) RETURN p LIMIT 50
```

A request the text cannot become gets a plain message that names the clause that failed and lists the grammar.
