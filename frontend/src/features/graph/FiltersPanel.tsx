import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { textInput, Field } from "./controls";
import { RULE_FIELDS, fieldOps, type RuleField, type RuleOp } from "./rules";
import { useGraphUi } from "./store";

/** Text filter and extra rules. Types, layers and depths are filtered in the legend (one control per action). */
export function FiltersPanel() {
  const ui = useGraphUi();
  return (
    <div className="flex flex-col gap-3">
      <Field label="Filter by slug or title">
        <input
          type="search"
          className={textInput}
          placeholder="Slug or title…"
          autoComplete="off"
          value={ui.search}
          onChange={(e) => ui.set({ search: e.target.value })}
        />
      </Field>
      <div className="flex flex-col gap-2">
        <span className="text-xs text-muted-foreground">Rules (all must match)</span>
        {ui.rules.map((r, i) => (
          <div key={i} className="grid grid-cols-[1fr_1fr] gap-1.5 rounded-md border p-1.5">
            <select
              aria-label="Include or exclude"
              className={`${textInput} bg-card`}
              value={r.mode}
              onChange={(e) => ui.patchRule(i, { mode: e.target.value as "include" | "exclude" })}
            >
              <option value="include">Include</option>
              <option value="exclude">Exclude</option>
            </select>
            <select
              aria-label="Field"
              className={`${textInput} bg-card`}
              value={r.field}
              onChange={(e) => {
                const f = e.target.value as RuleField;
                ui.patchRule(i, { field: f, op: fieldOps(f)[0] as RuleOp });
              }}
            >
              {RULE_FIELDS.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </select>
            <select
              aria-label="Operator"
              className={`${textInput} bg-card`}
              value={r.op}
              onChange={(e) => ui.patchRule(i, { op: e.target.value as RuleOp })}
            >
              {fieldOps(r.field).map((op) => (
                <option key={op} value={op}>
                  {op}
                </option>
              ))}
            </select>
            <div className="flex gap-1">
              <input
                aria-label="Value"
                className={textInput}
                placeholder="value"
                value={r.value}
                onChange={(e) => ui.patchRule(i, { value: e.target.value })}
              />
              <Button variant="ghost" size="icon" className="size-8 shrink-0" aria-label="Remove rule" onClick={() => ui.removeRule(i)}>
                <X aria-hidden />
              </Button>
            </div>
          </div>
        ))}
        <Button variant="secondary" size="sm" className="self-start" onClick={ui.addRule}>
          Add rule
        </Button>
      </div>
      <Button variant="outline" size="sm" className="self-start" onClick={ui.resetFilters}>
        Reset all filters
      </Button>
    </div>
  );
}
