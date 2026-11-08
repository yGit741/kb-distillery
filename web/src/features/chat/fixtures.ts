import type { ChatStatus } from "@/api";

/** A ChatStatus as /api/chat/status answers it: keys are hints only. */
export function chatStatus(over: Partial<ChatStatus> = {}): ChatStatus {
  return {
    key: true,
    key_origin: "personal",
    key_file: "~/.config/kb-distillery/api-key",
    key_hint: "sk-ant-…abcd",
    key_name: "personal",
    reset_day: 30,
    backend: "agent",
    agent: { available: true, version: "1.2.3" },
    auth: {
      mode: "api_key",
      active_key: "personal",
      keys: [{ name: "personal", origin: "file", hint: "sk-ant-…abcd" }],
      keys_dir: "~/.config/kb-distillery/keys",
      subscription: { logged_in: false, error: "run `claude login`" },
    },
    models: [{ id: "m1", label: "Model One" }],
    default_model: "m1",
    spend: { credit: 100, spent: 10, left: 90, turns: 3, cycle_start: "2026-10-01", next_reset: "2026-10-31", subscription_turns: 0 },
    claude: { available: true, reason: "" },
    ...over,
  };
}
