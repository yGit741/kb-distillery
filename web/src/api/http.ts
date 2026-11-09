import createClient from "openapi-fetch";
import { ApiError, type DataSource } from "./datasource";
import type { paths } from "./schema";
import type * as T_ from "./types";

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

  /** The import routes take a multipart .zip or JSON {git_url}, which the typed client cannot express: plain fetch. */
  async function postImport<T>(path: string, req: T_.KbImportRequest): Promise<T> {
    let init: RequestInit;
    if ("file" in req) {
      const form = new FormData();
      form.append("file", req.file, req.file.name);
      if (req.id) form.append("id", req.id);
      if (req.kit) form.append("kit", req.kit);
      init = { body: form };
    } else {
      init = { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ git_url: req.gitUrl, id: req.id || null, kit: req.kit || null }) };
    }
    let res: Response;
    try {
      res = await fetchImpl(path, { method: "POST", cache: "no-store", ...init });
    } catch (e) {
      throw new ApiError(`Could not reach ${path}: ${e instanceof Error ? e.message : String(e)}`);
    }
    const body: unknown = await res.json().catch(() => undefined);
    if (!res.ok) throw new ApiError(message(body, `${path} answered ${res.status}`), res.status);
    return body as T;
  }

  async function postRaw<T>(path: string, init: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await fetchImpl(path, { method: "POST", cache: "no-store", ...init });
    } catch (e) {
      throw new ApiError(`Could not reach ${path}: ${e instanceof Error ? e.message : String(e)}`);
    }
    const body: unknown = await res.json().catch(() => undefined);
    if (!res.ok) {
      const fallback = res.status === 405 ? "This knowledge base is read-only." : res.status === 413 ? "That is too large to add." : `${path} answered ${res.status}`;
      throw new ApiError(message(body, fallback), res.status);
    }
    return body as T;
  }

  return {
    kind: "http",

    getLifecycle: () => run(() => client.GET("/api/lifecycle"), "/api/lifecycle"),
    getShareStatus: () => run(() => client.GET("/api/share/status"), "/api/share/status"),
    getHealth: () => run(() => client.GET("/api/health"), "/api/health"),
    getKb: () => run(() => client.GET("/api/kb"), "/api/kb"),
    listKbs: () => run(() => client.GET("/api/kb/list"), "/api/kb/list"),
    previewKbImport: (req) => postImport<T_.KbImportPreview>("/api/kb/import/validate", req),
    importKb: (req) => postImport<T_.KbImportResult>("/api/kb/import", req),
    getKbInbox: () => run(() => client.GET("/api/kb/inbox"), "/api/kb/inbox"),
    pullKbInbox: () => run(() => client.POST("/api/kb/inbox/pull"), "/api/kb/inbox/pull"),
    addInboxFiles: (files) => {
      const form = new FormData();
      for (const f of files) form.append("files", f, f.name);
      return postRaw<T_.InboxAddResult>("/api/inbox/files", { body: form });
    },
    linkInboxFolder: (path) =>
      postRaw<T_.LinkFolderResult>("/api/inbox/link-folder", { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) }),
    getOps: (refresh) =>
      run(() => client.GET("/api/ops", { params: { query: refresh ? { refresh: "1" } : {} } }), "/api/ops"),

    getGraph: (opts) =>
      run(
        () =>
          client.GET("/api/graph", {
            params: { query: { ...(opts?.raw ? { layer: "raw" } : {}), ...(opts?.kbs?.length ? { kb: opts.kbs.join(",") } : {}) } },
          }),
        "/api/graph",
      ),
    getGraphNodes: async () => (await run(() => client.GET("/api/graph"), "/api/graph")).nodes,
    getCitations: () => run(() => client.GET("/api/citations"), "/api/citations"),
    listGraphQueries: () => run(() => client.GET("/api/graph/queries"), "/api/graph/queries"),
    runCypher: (query) => run(() => client.POST("/api/graph/cypher", { body: { query, limit: 500 } }), "/api/graph/cypher"),
    runGraphQuery: (name, params) =>
      run(
        () => client.POST("/api/graph/queries/{name}", { params: { path: { name } }, body: { params, limit: 500 } }),
        `/api/graph/queries/${name}`,
      ),

    shapeGraph: (text) => run(() => client.POST("/api/graph/shape", { body: { text, limit: 500 } }), "/api/graph/shape"),

    routeLine: (text, commands, opts) =>
      run(() => client.POST("/api/line/route", { body: { text, commands: commands.map((c) => ({ id: c.id, label: c.label })) }, ...(opts?.signal ? { signal: opts.signal } : {}) }), "/api/line/route"),
    layersFromText: (text, op, opts) =>
      run(() => client.POST("/api/graph/layers", { body: { text, op, ...(opts?.backend ? { backend: opts.backend } : {}), ...(opts?.fallback ? { fallback: opts.fallback } : {}) } }), "/api/graph/layers"),

    getRelationProposals: ({ min, max, kind }) =>
      run(
        () => client.GET("/api/relations/proposals", { params: { query: { min, max, ...(kind ? { kind } : {}) } } }),
        "/api/relations/proposals",
      ),

    listProposals: async (status) =>
      (await run(() => client.GET("/api/proposals", { params: { query: status ? { status } : {} } }), "/api/proposals")).proposals,
    getProposal: (id) => run(() => client.GET("/api/proposals/{pid}", { params: { path: { pid: id } } }), `/api/proposals/${id}`),
    getProposalRender: (id) =>
      run(() => client.GET("/api/proposals/{pid}/render", { params: { path: { pid: id } } }), `/api/proposals/${id}/render`),
    decideProposal: (id, d) =>
      run(
        () => client.POST("/api/proposals/{pid}/decisions", { params: { path: { pid: id } }, body: { hunk_id: d.hunk_id, decision: d.decision, comment: d.comment ?? "" } }),
        `/api/proposals/${id}/decisions`,
      ),
    applyProposal: (id) => run(() => client.POST("/api/proposals/{pid}/apply", { params: { path: { pid: id } } }), `/api/proposals/${id}/apply`),
    rejectProposal: (id, reason) =>
      run(() => client.POST("/api/proposals/{pid}/reject", { params: { path: { pid: id } }, body: { reason: reason ?? null } }), `/api/proposals/${id}/reject`),

    listViews: () => run(() => client.GET("/api/views"), "/api/views"),
    listReadyViews: () => run(() => client.GET("/api/views/ready"), "/api/views/ready"),
    listRecent: () => run(() => client.GET("/api/recent"), "/api/recent"),
    addRecent: (text, spec) => run(() => client.POST("/api/recent", { body: { text, spec: spec ?? {} } }), "/api/recent"),

    listPages: (opts) =>
      run(() => client.GET("/api/pages", { params: { query: opts?.kb ? { kb: opts.kb } : {} } }), "/api/pages"),
    getPage: (slug, opts) =>
      run(
        () => client.GET("/api/pages/{slug}", { params: { path: { slug }, query: opts?.kb ? { kb: opts.kb } : {} } }),
        `/api/pages/${slug}`,
      ),
    getPageSources: (slug, opts) =>
      run(
        () => client.GET("/api/pages/{slug}/sources", { params: { path: { slug }, query: opts?.kb ? { kb: opts.kb } : {} } }),
        `/api/pages/${slug}/sources`,
      ),
    postPageChat: (slug, body) =>
      run(() => client.POST("/api/pages/{slug}/chat", { params: { path: { slug } }, body }), `/api/pages/${slug}/chat`),
    getPageChat: (slug) => run(() => client.GET("/api/pages/{slug}/chat", { params: { path: { slug } } }), `/api/pages/${slug}/chat`),
    listPageFlags: (slug) => run(() => client.GET("/api/pages/{slug}/flags", { params: { path: { slug } } }), `/api/pages/${slug}/flags`),
    addPageFlag: (slug, body) =>
      run(() => client.POST("/api/pages/{slug}/flags", { params: { path: { slug } }, body }), `/api/pages/${slug}/flags`),
    deletePageFlag: async (slug, id) => {
      await run(() => client.DELETE("/api/pages/{slug}/flags/{flag_id}", { params: { path: { slug, flag_id: id } } }), `/api/pages/${slug}/flags/${id}`);
    },
    fixPageFlags: (slug) =>
      run(() => client.POST("/api/pages/{slug}/flags/fix", { params: { path: { slug } }, body: {} }), `/api/pages/${slug}/flags/fix`),
    searchMentions: async (q) =>
      (await run(() => client.GET("/api/pages/mentions", { params: { query: { q } } }), "/api/pages/mentions")).pages,
    getPageSource: async (slug) => {
      const path = `/api/pages/${encodeURIComponent(slug)}/source`;
      let res: Response;
      try {
        res = await fetchImpl(path, { cache: "no-store" });
      } catch (e) {
        throw new ApiError(`Could not reach ${path}: ${e instanceof Error ? e.message : String(e)}`);
      }
      if (!res.ok) throw new ApiError(`${path} answered ${res.status}`, res.status);
      return res.text();
    },
    search: (q, limit) =>
      run(
        () => client.GET("/api/search", { params: { query: { q, ...(limit ? { limit: String(limit) } : {}) } } }),
        "/api/search",
      ),
    searchText: (q, opts) =>
      run(
        () =>
          client.GET("/api/search/text", {
            params: { query: { q, ...(opts?.kinds?.length ? { kinds: opts.kinds.join(",") } : {}), ...(opts?.limit ? { limit: opts.limit } : {}) } },
            ...(opts?.signal ? { signal: opts.signal } : {}),
          }),
        "/api/search/text",
      ),
    searchSimilar: ({ q, slug, k }, signal) =>
      run(
        () => client.GET("/api/search/similar", { params: { query: { ...(slug ? { slug } : { q: q ?? "" }), ...(k ? { k } : {}) } }, signal }),
        "/api/search/similar",
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
    getVideo: (path) =>
      run(() => client.GET("/api/videos/{path}", { params: { path: { path } } }), `/api/videos/${path}`),
    digestRaw: (path) =>
      run(() => client.POST("/api/raw/{path}/digest", { params: { path: { path } } }), `/api/raw/${path}/digest`),

    previewDigest: (raws, backend) =>
      run(() => client.POST("/api/digest/preview", { body: { raws, ...(backend ? { backend } : {}) } }), "/api/digest/preview"),
    startDigestJob: (raws, backend) =>
      run(() => client.POST("/api/digest/jobs", { body: { raws, ...(backend ? { backend } : {}) } }), "/api/digest/jobs"),
    listDigestJobs: () => run(() => client.GET("/api/digest/jobs"), "/api/digest/jobs"),
    cancelDigestJob: (id) =>
      run(() => client.DELETE("/api/digest/jobs/{job_id}", { params: { path: { job_id: id } } }), `/api/digest/jobs/${id}`),

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

    listBacklog: () => run(() => client.GET("/api/backlog"), "/api/backlog"),
    listThink: () => run(() => client.GET("/api/think"), "/api/think"),
    getThinkNote: (name) => run(() => client.GET("/api/think/{name}", { params: { path: { name } } }), `/api/think/${name}`),
    saveThinkNote: (name, body) =>
      run(() => client.PUT("/api/think/{name}", { params: { path: { name } }, body }), `/api/think/${name}`),
    captureThink: (text) => run(() => client.POST("/api/think/capture", { body: { text } }), "/api/think/capture"),

    getChatStatus: () => run(() => client.GET("/api/chat/status"), "/api/chat/status"),
    getChatSettings: () => run(() => client.GET("/api/chat/settings"), "/api/chat/settings"),
    updateChatSettings: (body) => run(() => client.POST("/api/chat/settings", { body }), "/api/chat/settings"),
    getChatPrompts: () => run(() => client.GET("/api/chat/prompts"), "/api/chat/prompts"),
    getChatKeys: () => run(() => client.GET("/api/chat/keys"), "/api/chat/keys"),
    addChatKey: (body) => run(() => client.POST("/api/chat/keys", { body }), "/api/chat/keys"),
    removeChatKey: (name) =>
      run(() => client.DELETE("/api/chat/keys/{name}", { params: { path: { name } } }), `/api/chat/keys/${name}`),
    listSessions: () => run(() => client.GET("/api/sessions"), "/api/sessions"),
    getSession: (id) => run(() => client.GET("/api/sessions/{session_id}", { params: { path: { session_id: id } } }), `/api/sessions/${id}`),
    putSession: (id, body) =>
      run(() => client.PUT("/api/sessions/{session_id}", { params: { path: { session_id: id } }, body }), `/api/sessions/${id}`),
    renameSession: (id, title) =>
      run(() => client.PATCH("/api/sessions/{session_id}", { params: { path: { session_id: id } }, body: { title } }), `/api/sessions/${id}`),
    deleteSession: (id) =>
      run(() => client.DELETE("/api/sessions/{session_id}", { params: { path: { session_id: id } } }), `/api/sessions/${id}`),
    listChatSkills: (session) =>
      run(() => client.GET("/api/chat/skills", { params: { query: session ? { session } : {} } }), "/api/chat/skills"),
    putChatSkills: (id, body) =>
      run(() => client.PUT("/api/chat/skills/{session_id}", { params: { path: { session_id: id } }, body }), `/api/chat/skills/${id}`),
    saveChat: (body) => run(() => client.POST("/api/chat/saved", { body }), "/api/chat/saved"),
    answerChat: (body) => run(() => client.POST("/api/chat/answer", { body }), "/api/chat/answer"),
    sendChatMessage: (body) => run(() => client.POST("/api/chat/message", { body }), "/api/chat/message"),
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
