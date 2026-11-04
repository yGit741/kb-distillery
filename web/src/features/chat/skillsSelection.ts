import { flag } from "@/flags";

/** The skills switched on for each chat (agent mode). The panel writes it, the send path reads it without a hook;
 *  a chat with no entry (or the flag off) sends nothing, so the server uses the kb's whole whitelist. */
const chosen = new Map<string, string[]>();
const idOf = (chatId: string) => chatId.replace(/^kb-chat:/, "");

export const setSkillSelection = (chatId: string, names: string[] | undefined): void => {
  if (names) chosen.set(idOf(chatId), names);
  else chosen.delete(idOf(chatId));
};

/** What the chat request carries (spread into its body): the loaded subset, and the stored id so the server can apply the
 *  saved subset when the panel has not loaded it. Empty with the flag off, so that request is unchanged. */
export const skillsRequest = (chatId: string): { skills?: string[]; skills_session?: string } =>
  flag("agent-mode") ? { skills: skillSelection(chatId), skills_session: idOf(chatId) } : {};

/** `kb-chat:<id>` or the bare session id. */
export const skillSelection = (chatId: string): string[] | undefined =>
  flag("agent-mode") ? chosen.get(idOf(chatId)) : undefined;
