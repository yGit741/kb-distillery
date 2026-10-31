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

  // pages
  listPages(opts?: { kb?: string }): Promise<T.PageIndex>;
  /** `kb`: read the page from another knowledge base (the result is `read_only`). */
  getPage(slug: string, opts?: { kb?: string }): Promise<T.PageDetail>;
  search(q: string, limit?: number): Promise<T.SearchResult>;
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
  /** POST /api/chat; the caller reads `response.body` as server-sent events. */
  chatStream(body: T.ChatRequest, signal?: AbortSignal): Promise<Response>;

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
