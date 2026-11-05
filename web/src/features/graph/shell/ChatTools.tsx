import { useState } from "react";
import { PlanPanel } from "@/features/chat/PlanPanel";
import { PromptPanel } from "@/features/chat/PromptPanel";
import { SkillsPanel } from "@/features/chat/SkillsPanel";
import { isCustom, pick, setEdit, type Edits, type Prompt } from "@/features/chat/prompts";
import type { TodoItem } from "@/features/chat/sse";
import { readJson, writeJson } from "@/features/chat/storage";

/**
 * The plan, skills and prompts of the chat, in a sheet under the chat column's header (flag `chat-full`). The
 * template and its edits are stored under the keys the other chat surfaces read, so they apply to the next message.
 */
export function ChatTools({ prompts, todo, busy, sessionId }: { prompts: Prompt[]; todo: TodoItem[] | undefined; busy: boolean; sessionId: string }) {
  const [templateId, setTemplateId] = useState(() => readJson("local", "kbchat.template", "query"));
  const [edits, setEdits] = useState<Edits>(() => readJson("local", "kbchat.edits", {}));
  const current = pick(prompts, templateId);
  const save = (next: Edits) => {
    setEdits(next);
    writeJson("local", "kbchat.edits", next);
  };
  return (
    <div data-testid="chat-tools" className="flex max-h-[60%] flex-col gap-3 overflow-y-auto border-b bg-card px-5 py-3">
      {todo && todo.length > 0 ? <PlanPanel items={todo} busy={busy} placement="header" /> : <p className="text-xs text-muted-foreground">No plan yet: the agent writes one when a task has steps.</p>}
      <SkillsPanel sessionId={sessionId} />
      <PromptPanel
        prompts={prompts}
        current={current}
        edits={edits}
        onTemplate={(id) => {
          setTemplateId(id);
          writeJson("local", "kbchat.template", id);
        }}
        onEdit={(text) => current && save(setEdit(current, edits, text))}
        onReset={() => {
          if (!current || !isCustom(current, edits)) return;
          const next = { ...edits };
          delete next[current.id];
          save(next);
        }}
      />
    </div>
  );
}
