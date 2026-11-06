import type * as T from "./types";

/** Everything a screen may ask for. Screens depend on this interface only, never on fetch or globals. */
export interface DataSource {
  readonly kind: "http" | "embedded";

  // lifecycle, share, health, ops
  getLifecycle(): Promise<T.LifecycleSnapshot>;
  getShareStatus(): Promise<T.ShareStatus>;
  getHealth(): Promise<T.HealthSnapshot>;
  /** The knowledge base this app serves (kb.toml, folder, git, types) and the ones the explorer can load. */
  getKb(): Promise<T.KbInfo>;
  listKbs(): Promise<T.KbList>;
  /** Local app only: dry run of importing an OKF bundle (.zip upload or git URL) as a new knowledge base. */
  previewKbImport(req: T.KbImportRequest): Promise<T.KbImportPreview>;
  /** Local app only: import it. */
  importKb(req: T.KbImportRequest): Promise<T.KbImportResult>;
  /** Local app only: the deployed site's upload inbox (pending, imported, failed) as the server reads it. */
  getKbInbox(): Promise<T.KbInbox>;
  /** Local app only: import every pending upload as a new knowledge base and report back to the site. */
  pullKbInbox(): Promise<T.KbInboxPull>;
  getOps(refresh?: boolean): Promise<T.OpsSnapshot>;

  // graph
  /** `kbs`: other knowledge bases to show (read-only); several share one canvas with ids `<kb>:<slug>`. */
  getGraph(opts?: { raw?: boolean; kbs?: readonly string[] }): Promise<T.GraphSnapshot>;
  /** Vault nodes: layer, type, depth, status, areas. */
  getGraphNodes(): Promise<T.GraphNode[]>;
  getCitations(): Promise<T.CitationGraph>;
  /** Read-only graph queries (local app only): the named ones, a Cypher query (supported subset), a named one. */
  listGraphQueries(): Promise<T.NamedQuery[]>;
  runCypher(query: string): Promise<T.QueryTable>;
  runGraphQuery(name: string, params: Record<string, string>): Promise<T.QueryTable>;
  /** Free text (or Cypher, or a style clause list) to a graph view: the pages as rows plus the style (local app only). */
  shapeGraph(text: string): Promise<T.ShapeResult>;
  /** LLM relation proposals in a confidence range 0..1 (local app only), best first, with a 10-bucket histogram. */
  getRelationProposals(opts: { min: number; max: number; kind?: string }): Promise<T.RelationProposals>;

  // pinned views (meta/views.json) and the recent steps of the graph search panel (local, never committed)
  listViews(): Promise<T.ViewList>;
  listRecent(): Promise<T.RecentList>;
  addRecent(text: string, spec?: Record<string, unknown>): Promise<T.RecentList>;

  // pages
  listPages(opts?: { kb?: string }): Promise<T.PageIndex>;
  /** `kb`: read the page from another knowledge base (the result is `read_only`). */
  getPage(slug: string, opts?: { kb?: string }): Promise<T.PageDetail>;
  /** The page file as stored (frontmatter and body); the OKF export copies it. */
  getPageSource(slug: string): Promise<string>;
  search(q: string, limit?: number): Promise<T.SearchResult>;
  /** Tier 2 of the search line: full text over pages, think notes, chats and raw text (the embedded share has none). */
  searchText(q: string, opts?: { kinds?: readonly string[]; limit?: number; signal?: AbortSignal }): Promise<T.TextSearch>;
  findPath(a: string, b: string): Promise<T.PathResult>;

  // pipeline, corpus, raw
  getPipeline(): Promise<T.PipelineSnapshot>;
  getCorpus(format?: string): Promise<T.CorpusTable>;
  getRawPreview(path: string): Promise<T.RawPreview>;
  /** One source's raw file as a Home card: live from `path` (local), baked per `slug` (share). */
  getRawCard(slug: string, path: string | null): Promise<T.RawCard>;
  /** Image URL of page 1 / the image itself, or null where only baked data URIs exist. */
  rawThumbUrl(path: string, width: number): string | null;
  /** The raw file itself (local only). */
  rawFileUrl(path: string): string | null;
  digestRaw(path: string): Promise<T.DigestResult>;
  /** A scrap-youtube bundle by its raw item `raw/videos/<dir>/video.md` (local only). */
  getVideo(path: string): Promise<T.VideoBundle>;

  // scopes
  listScopes(): Promise<T.ScopeList>;
  getScope(slug: string): Promise<T.ScopeDetail>;
  resolveScope(body: T.ScopeResolveRequest): Promise<T.ScopeResolved>;
  saveScope(body: T.ScopeSaveRequest): Promise<T.ScopeStep>;
  deleteScope(slug: string): Promise<T.ScopeStep>;
  duplicateScope(slug: string, body: T.ScopeDuplicateRequest): Promise<T.ScopeStep>;

  // chat (the answer itself streams as SSE: use chatStream)
  getChatStatus(): Promise<T.ChatStatus>;
  getChatSettings(): Promise<T.ChatSettings>;
  updateChatSettings(body: T.ChatSettingsUpdate): Promise<T.ChatStatus>;
  getChatPrompts(): Promise<T.PromptsResponse>;
  getChatKeys(): Promise<T.KeyList>;
  addChatKey(body: T.KeyAdd): Promise<T.ChatStatus>;
  removeChatKey(name: string): Promise<T.ChatStatus>;
  saveChat(body: T.SavedChat): Promise<T.SavedChatResult>;
  /** POST /api/chat/message: queue a message into the running agent turn (rejects with a 404 when none is live). */
  sendChatMessage(body: T.ChatMessageIn): Promise<T.ChatMessageResult>;
  /** POST /api/chat; the caller reads `response.body` as server-sent events. */
  /** POST /api/chat/answer: the reply to an `ask` event. */
  answerChat(body: T.ChatAnswer): Promise<T.ChatAnswerResult>;
  chatStream(body: T.ChatRequest, signal?: AbortSignal): Promise<Response>;

  // chat sessions (local app only; never in share builds)
  listSessions(): Promise<T.SessionList>;
  getSession(id: string): Promise<T.SessionDoc>;
  /** Create or replace the whole document. */
  putSession(id: string, body: T.SessionPutRequest): Promise<T.SessionDoc>;
  renameSession(id: string, title: string): Promise<T.SessionDoc>;
  deleteSession(id: string): Promise<T.SessionDeleted>;

  /** GET /api/chat/skills: the kb's whitelisted skills and which are on for `session` (agent mode only). */
  listChatSkills(session?: string): Promise<T.ChatSkillList>;
  /** PUT /api/chat/skills/{id}: the skills that are on for one session. */
  putChatSkills(id: string, body: T.ChatSkillsPut): Promise<T.ChatSkillList>;

  // think (local app only; never in share builds)
  listThink(): Promise<T.ThinkList>;
  getThinkNote(name: string): Promise<T.ThinkNote>;
  saveThinkNote(name: string, body: T.ThinkSaveRequest): Promise<T.ThinkWriteResult>;
  captureThink(text: string): Promise<T.ThinkWriteResult>;

  // backlog (local app only; never in share builds)
  listBacklog(): Promise<T.BacklogList>;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
