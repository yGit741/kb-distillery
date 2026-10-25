import createClient from "openapi-fetch";
import { ApiError, type DataSource } from "./datasource";
import type { paths } from "./schema";

export type Fetch = typeof fetch;

type Result<T> = { data?: T; error?: unknown; response: Response };

function message(error: unknown, fallback: string): string {
  if (error && typeof error === "object") {
    const e = (error as { error?: unknown; detail?: unknown }).error ?? (error as { detail?: unknown }).detail;
    if (typeof e === "string") return e;
  }
  return fallback;
}

const encodePath = (p: string) => p.split("/").map(encodeURIComponent).join("/");

/** Live backend, typed from the generated OpenAPI `paths`. Paths already start with /api. */
export function createHttpDataSource(fetchImpl: Fetch = (...a) => fetch(...a), baseUrl?: string): DataSource {
  const client = createClient<paths>({
    baseUrl: baseUrl ?? (globalThis.location?.origin || "http://localhost"),
    fetch: (req) => fetchImpl(req),
    headers: { Accept: "application/json" },
    cache: "no-store",
  } as Parameters<typeof createClient<paths>>[0]);

  async function run<T>(call: () => Promise<Result<T>>, what: string): Promise<T> {
    let r: Result<T>;
    try {
      r = await call();
    } catch (e) {
      throw new ApiError(`Could not reach ${what}: ${e instanceof Error ? e.message : String(e)}`);
    }
    if (!r.response.ok) throw new ApiError(message(r.error, `${what} answered ${r.response.status}`), r.response.status);
    if (r.data === undefined) throw new ApiError(`${what} did not return JSON`, r.response.status);
    return r.data;
  }

  return {
    kind: "http",

    getLifecycle: () => run(() => client.GET("/api/lifecycle"), "/api/lifecycle"),
    getShareStatus: () => run(() => client.GET("/api/share/status"), "/api/share/status"),
    getHealth: () => run(() => client.GET("/api/health"), "/api/health"),
    getOps: (refresh) =>
      run(() => client.GET("/api/ops", { params: { query: refresh ? { refresh: "1" } : {} } }), "/api/ops"),

    getGraph: (opts) =>
      run(() => client.GET("/api/graph", { params: { query: opts?.raw ? { layer: "raw" } : {} } }), "/api/graph"),
    getGraphNodes: async () => (await run(() => client.GET("/api/graph"), "/api/graph")).nodes,
    getCitations: () => run(() => client.GET("/api/citations"), "/api/citations"),

    listPages: () => run(() => client.GET("/api/pages"), "/api/pages"),
    getPage: (slug) => run(() => client.GET("/api/pages/{slug}", { params: { path: { slug } } }), `/api/pages/${slug}`),
    search: (q, limit) =>
      run(
        () => client.GET("/api/search", { params: { query: { q, ...(limit ? { limit: String(limit) } : {}) } } }),
        "/api/search",
      ),
    findPath: (a, b) => run(() => client.GET("/api/path", { params: { query: { a, b } } }), "/api/path"),

    getPipeline: () => run(() => client.GET("/api/pipeline"), "/api/pipeline"),
    getCorpus: (format) =>
      run(() => client.GET("/api/corpus", { params: { query: format ? { format } : {} } }), "/api/corpus"),
    getRawCard: async (_slug, path) => {
      if (!path) throw new ApiError("this source has no raw file", 404);
      return run(() => client.GET("/api/raw/{path}/card", { params: { path: { path } } }), `/api/raw/${path}/card`);
    },
    rawThumbUrl: (path, width) => `${baseUrl ?? (globalThis.location?.origin || "")}/api/raw/${encodePath(path)}/thumb?w=${width}`,
    rawFileUrl: (path) => `${baseUrl ?? (globalThis.location?.origin || "")}/api/raw/${encodePath(path)}/file`,
    getRawPreview: (path) =>
      run(() => client.GET("/api/raw/{path}", { params: { path: { path } } }), `/api/raw/${path}`),
    digestRaw: (path) =>
      run(() => client.POST("/api/raw/{path}/digest", { params: { path: { path } } }), `/api/raw/${path}/digest`),

    listScopes: () => run(() => client.GET("/api/scopes"), "/api/scopes"),
    getScope: (slug) => run(() => client.GET("/api/scopes/{slug}", { params: { path: { slug } } }), `/api/scopes/${slug}`),
    resolveScope: (body) => run(() => client.POST("/api/scopes/resolve", { body }), "/api/scopes/resolve"),
    saveScope: (body) => run(() => client.POST("/api/scopes", { body }), "/api/scopes"),
    deleteScope: (slug) =>
      run(() => client.DELETE("/api/scopes/{slug}", { params: { path: { slug } } }), `/api/scopes/${slug}`),
    duplicateScope: (slug, body) =>
      run(
        () => client.POST("/api/scopes/{slug}/duplicate", { params: { path: { slug } }, body }),
        `/api/scopes/${slug}/duplicate`,
      ),

    getChatStatus: () => run(() => client.GET("/api/chat/status"), "/api/chat/status"),
    getChatSettings: () => run(() => client.GET("/api/chat/settings"), "/api/chat/settings"),
    updateChatSettings: (body) => run(() => client.POST("/api/chat/settings", { body }), "/api/chat/settings"),
    getChatPrompts: () => run(() => client.GET("/api/chat/prompts"), "/api/chat/prompts"),
    getChatKeys: () => run(() => client.GET("/api/chat/keys"), "/api/chat/keys"),
    addChatKey: (body) => run(() => client.POST("/api/chat/keys", { body }), "/api/chat/keys"),
    removeChatKey: (name) =>
      run(() => client.DELETE("/api/chat/keys/{name}", { params: { path: { name } } }), `/api/chat/keys/${name}`),
    saveChat: (body) => run(() => client.POST("/api/chat/saved", { body }), "/api/chat/saved"),
    chatStream: async (body, signal) => {
      let res: Response;
      try {
        res = await fetchImpl("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify(body),
          signal,
        });
      } catch (e) {
        throw new ApiError(`Could not reach /api/chat: ${e instanceof Error ? e.message : String(e)}`);
      }
      if (!res.ok) {
        let body: unknown;
        try {
          body = await res.json();
        } catch {
          body = undefined;
        }
        const o = body && typeof body === "object" ? (body as { error?: unknown; hint?: unknown }) : {};
        const err = typeof o.error === "string" ? o.error : "";
        const hint = typeof o.hint === "string" ? o.hint : "";
        throw new ApiError(err ? (hint ? `${err} ${hint}` : err) : `/api/chat answered ${res.status}`, res.status);
      }
      return res;
    },
  };
}
