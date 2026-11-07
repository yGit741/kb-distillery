import type { ShareBlob } from "@/share/blob";
import { findPaths, searchPages } from "@/share/search";
import { sourceOf } from "@/lib/okf/pageSource";
import { ApiError, type DataSource } from "./datasource";

const NOT_SHARED = "not available in the shared view";

/**
 * Static share build: the data is a JSON blob baked into the page (`<script id="kb-data">`, read into
 * `globalThis.KB_EMBEDDED` by main.tsx). Read-only: graph, pages, page detail, search, shortest path,
 * the lifecycle snapshot (private profile) and the share status chip (always empty here). Everything
 * else (chat, ops, health, pipeline, raw, corpus, scopes, digest) rejects with a 404 ApiError; the
 * share builds do not even include those screens, this is the safety net for shared components.
 *
 * Without a blob (unit tests, a normal app load) every method rejects, as before.
 */
export function createEmbeddedDataSource(blob: ShareBlob | undefined = globalThis.KB_EMBEDDED): DataSource {
  const absent = async (): Promise<never> => {
    throw new ApiError(blob ? NOT_SHARED : "embedded data source: no data baked into this page", 404);
  };
  const base: DataSource = {
    kind: "embedded",
    getLifecycle: absent,
    getShareStatus: absent,
    getHealth: absent,
    getKb: absent,
    listKbs: absent,
    previewKbImport: absent,
    importKb: absent,
    getKbInbox: absent,
    pullKbInbox: absent,
    getOps: absent,
    getGraph: absent,
    getGraphNodes: absent,
    getCitations: absent,
    listGraphQueries: absent,
    runCypher: absent,
    runGraphQuery: absent,
    shapeGraph: absent,
    layersFromText: absent,
    getRelationProposals: absent,
    listViews: absent,
    listReadyViews: absent,
    listRecent: absent,
    addRecent: absent,
    listPages: absent,
    getPage: absent,
    getPageSource: absent,
    search: absent,
    searchText: absent,
    findPath: absent,
    getPipeline: absent,
    getCorpus: absent,
    getRawPreview: absent,
    getRawCard: absent,
    rawThumbUrl: () => null,
    rawFileUrl: () => null,
    digestRaw: absent,
    getVideo: absent,
    listScopes: absent,
    getScope: absent,
    resolveScope: absent,
    saveScope: absent,
    deleteScope: absent,
    duplicateScope: absent,
    getChatStatus: absent,
    getChatSettings: absent,
    updateChatSettings: absent,
    getChatPrompts: absent,
    getChatKeys: absent,
    addChatKey: absent,
    removeChatKey: absent,
    saveChat: absent,
    answerChat: absent,
    sendChatMessage: absent,
    chatStream: absent,
    listSessions: absent,
    getSession: absent,
    putSession: absent,
    renameSession: absent,
    deleteSession: absent,
    listChatSkills: absent,
    putChatSkills: absent,
    listBacklog: absent,
    listThink: absent,
    getThinkNote: absent,
    saveThinkNote: absent,
    captureThink: absent,
  };
  if (!blob) return base;
  const data = blob;
  return {
    ...base,
    getGraph: async () => data.graph,
    getGraphNodes: async () => data.graph.nodes,
    listPages: async () => data.index,
    getPage: async (slug) => {
      const page = data.pages[slug];
      if (!page) throw new ApiError("not found", 404);
      return page;
    },
    getPageSource: async (slug) => {
      const page = data.pages[slug];
      if (!page) throw new ApiError("not found", 404);
      return sourceOf(page.frontmatter, page.markdown);
    },
    search: async (q, limit) => searchPages(data, q, limit),
    searchText: async (q) => ({ query: q, hits: [] }),
    findPath: async (a, b) => {
      const r = findPaths(data, a, b);
      if (!r) throw new ApiError("not found", 404);
      return r;
    },
    getCitations: async () => {
      if (!data.citations) throw new ApiError(NOT_SHARED, 404);
      return data.citations;
    },
    getLifecycle: async () => {
      if (!data.lifecycle) throw new ApiError(NOT_SHARED, 404);
      const l = data.lifecycle;
      // The snapshot was captured by the share builder: no local policy state, JSON-safe stats keys.
      return { ...l, policy: { ...l.policy, hooks_installed: l.policy?.hooks_installed ?? false } };
    },
    getShareStatus: async () => ({ status: null, chip: null }),
    getRawCard: async (slug) => {
      const card = data.rawCards?.[slug];
      if (!card) throw new ApiError(NOT_SHARED, 404);
      return card;
    },
  };
}
