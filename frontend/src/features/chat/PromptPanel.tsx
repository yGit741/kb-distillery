import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "./fields";
import { isCustom, systemFor, type Edits, type Prompt } from "./prompts";

interface Props {
  prompts: Prompt[];
  current: Prompt | undefined;
  edits: Edits;
  onTemplate: (id: string) => void;
  onEdit: (text: string) => void;
  onReset: () => void;
}

export function PromptPanel({ prompts, current, edits, onTemplate, onEdit, onReset }: Props) {
  if (!current) return null;
  return (
    <details className="rounded-md border bg-card px-3 py-2 text-sm">
      <summary className="flex cursor-pointer flex-wrap items-center gap-x-2">
        <span className="text-muted-foreground">Prompt:</span>
        <strong>{current.title}</strong>
        {isCustom(current, edits) && <Badge variant="primary">custom</Badge>}
        {current.description && <span className="hidden truncate text-xs text-muted-foreground sm:inline">· {current.description}</span>}
      </summary>
      <div className="mt-2 flex flex-col gap-2">
        <div className="flex gap-2">
          <Select value={current.id} onChange={(e) => onTemplate(e.target.value)} aria-label="Prompt template">
            {prompts.map((p) => (
              <option key={p.id} value={p.id}>{p.title}</option>
            ))}
          </Select>
          <Button variant="ghost" size="sm" className="h-9" onClick={onReset} disabled={!isCustom(current, edits)}>
            Reset
          </Button>
        </div>
        <textarea
          className="w-full rounded-md border bg-background p-2 font-mono text-xs"
          rows={7}
          spellCheck
          aria-label="System prompt"
          value={systemFor(current, edits)}
          onChange={(e) => onEdit(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">
          Edits are kept per template in this browser and apply from the next message. The retrieved pages and the citation rules are always appended.
        </p>
      </div>
    </details>
  );
}
