import type * as T from "./types";

/** Everything a screen may ask for. Screens depend on this interface only, never on fetch or globals. */
export interface DataSource {
  readonly kind: "http" | "embedded";

  // lifecycle, share, health, ops
  getLifecycle(): Promise<T.LifecycleSnapshot>;
  getShareStatus(): Promise<T.ShareStatus>;
  getHealth(): Promise<T.HealthSnapshot>;
  getOps(refresh?: boolean): Promise<T.OpsSnapshot>;

  // graph
  getGraph(opts?: { raw?: boolean }): Promise<T.GraphSnapshot>;
  /** Vault nodes: layer, type, depth, status, areas. */
  getGraphNodes(): Promise<T.GraphNode[]>;
  getCitations(): Promise<T.CitationGraph>;

  // pages
  listPages(): Promise<T.PageIndex>;
  getPage(slug: string): Promise<T.PageDetail>;
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
