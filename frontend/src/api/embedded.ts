import type { DataSource } from "./datasource";

/** Static share build: data baked into a global JSON blob. Not wired yet (Phase 5). */
export function createEmbeddedDataSource(): DataSource {
  const notBuilt = async (): Promise<never> => {
    throw new Error("embedded data source: not built for share yet");
  };
  return {
    kind: "embedded",
    getLifecycle: notBuilt,
    getShareStatus: notBuilt,
    getHealth: notBuilt,
    getOps: notBuilt,
    getGraph: notBuilt,
    getGraphNodes: notBuilt,
    getCitations: notBuilt,
    listPages: notBuilt,
    getPage: notBuilt,
    search: notBuilt,
    findPath: notBuilt,
    getPipeline: notBuilt,
    getCorpus: notBuilt,
    getRawPreview: notBuilt,
    digestRaw: notBuilt,
    listScopes: notBuilt,
    getScope: notBuilt,
    resolveScope: notBuilt,
    saveScope: notBuilt,
    deleteScope: notBuilt,
    duplicateScope: notBuilt,
    getChatStatus: notBuilt,
    getChatSettings: notBuilt,
    updateChatSettings: notBuilt,
    getChatPrompts: notBuilt,
    getChatKeys: notBuilt,
    addChatKey: notBuilt,
    removeChatKey: notBuilt,
    saveChat: notBuilt,
    chatStream: notBuilt,
  };
}
