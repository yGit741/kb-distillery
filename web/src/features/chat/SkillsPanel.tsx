import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useDataSource, type ChatSkillList } from "@/api";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useFlag } from "@/flags/useFlag";
import { setSkillSelection } from "./skillsSelection";

export const skillsKey = (sessionId: string) => ["chat", "skills", sessionId] as const;

const namesOn = (list: ChatSkillList) => list.skills.filter((s) => s.enabled).map((s) => s.name);

/** The kb's whitelisted skills, one row each with a toggle, saved per session (flag `agent-mode`; renders nothing off). */
export function SkillsPanel({ sessionId }: { sessionId: string }) {
  const ds = useDataSource();
  const on = useFlag("agent-mode") && ds.kind === "http";
  if (!on) return null;
  return <SkillsList sessionId={sessionId} />;
}

function SkillsList({ sessionId }: { sessionId: string }) {
  const ds = useDataSource();
  const qc = useQueryClient();
  const key = skillsKey(sessionId);
  const list = useQuery({ queryKey: key, queryFn: () => ds.listChatSkills(sessionId) });
  const data = list.data;

  useEffect(() => {
    setSkillSelection(sessionId, data && data.skills.length ? namesOn(data) : undefined);
  }, [sessionId, data]);

  const save = useMutation({
    mutationFn: (enabled: string[]) => ds.putChatSkills(sessionId, { enabled }),
    onMutate: async (enabled) => {
      await qc.cancelQueries({ queryKey: key });
      const before = qc.getQueryData<ChatSkillList>(key);
      if (before) qc.setQueryData<ChatSkillList>(key, { ...before, skills: before.skills.map((s) => ({ ...s, enabled: enabled.includes(s.name) })) });
      return { before };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.before) qc.setQueryData(key, ctx.before);
    },
    onSuccess: (saved) => qc.setQueryData(key, saved),
  });

  const toggle = (name: string, next: boolean) => {
    if (!data) return;
    const current = namesOn(data);
    save.mutate(data.skills.map((s) => s.name).filter((n) => (n === name ? next : current.includes(n))));
  };

  return (
    <section className="flex flex-col gap-1" aria-label="Skills">
      <h3 className="text-xs font-medium">Skills</h3>
      {list.isPending ? (
        <div role="status" aria-label="Loading skills" className="flex flex-col gap-2">
          <Skeleton className="h-8" />
          <Skeleton className="h-8" />
        </div>
      ) : list.isError ? (
        <p role="alert" className="break-words text-xs text-bad">
          Could not load skills: {list.error instanceof Error ? list.error.message : String(list.error)}{" "}
          <button type="button" className="text-primary underline" onClick={() => void list.refetch()}>Try again</button>
        </p>
      ) : list.data.skills.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No skills whitelisted for this knowledge base. List names under <code>skills</code> in the <code>[agent]</code> table of its <code>kb.toml</code>.
        </p>
      ) : (
        <ul className="flex flex-col divide-y">
          {list.data.skills.map((s) => (
            <li key={s.name} className="flex items-start gap-3 py-2 first:pt-1">
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <span id={`skill-${s.name}`} className="break-words text-sm">{s.name}</span>
                {s.description && <span id={`skill-${s.name}-desc`} className="text-xs text-muted-foreground">{s.description}</span>}
              </div>
              <Switch
                checked={s.enabled}
                onCheckedChange={(next) => toggle(s.name, next)}
                aria-labelledby={`skill-${s.name}`}
                aria-describedby={s.description ? `skill-${s.name}-desc` : undefined}
                className="mt-0.5"
              />
            </li>
          ))}
        </ul>
      )}
      {save.isError && (
        <p role="alert" className="break-words text-xs text-bad">Could not save: {save.error instanceof Error ? save.error.message : String(save.error)}</p>
      )}
    </section>
  );
}
