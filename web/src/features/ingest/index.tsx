import { useNavigate, useSearch } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import { useVariant } from "@/components/variants";
import { useFlag } from "@/flags/useFlag";
import { LifecycleScreen } from "@/features/lifecycle/LifecycleScreen";
import { PipelineScreen } from "@/features/pipeline/PipelineScreen";
import { HealthView } from "@/features/system/HealthView";
import type { HealthLike } from "@/features/system/model";
import { useApiQuery } from "@/lib/useApiQuery";
import { INGEST_TABS, type IngestTab, type SearchById } from "@/routes/search";
import { useIngestFlow } from "./model";
import { SingleLayout } from "./Single";
import { WizardLayout } from "./Wizard";
import { IngestOverview } from "./Overview";

const TAB_LABEL: Record<IngestTab, string> = { overview: "Overview", pipeline: "Pipeline", health: "Health", history: "History" };

/** The add flow without its page header: the Add card on the split Overview. */
function AddBody() {
  const [layout] = useVariant("ingest-layout", ["single", "wizard"], "single");
  const wizard = layout === "wizard";
  const flow = useIngestFlow({ inbox: !wizard });
  return wizard ? <WizardLayout flow={flow} /> : <SingleLayout flow={flow} />;
}

/** The add flow: drop a source, say what it is, watch the job, review the proposal. Layout is the `ingest-layout` variant. */
function AddFlow() {
  const [layout] = useVariant("ingest-layout", ["single", "wizard"], "single");
  const wizard = layout === "wizard";
  const flow = useIngestFlow({ inbox: !wizard });
  return (
    <div className={cn("mx-auto flex w-full flex-col gap-5 px-4 pt-6 pb-10", wizard ? "max-w-xl" : "max-w-2xl")}>
      <header>
        <h1 className="text-xl font-semibold">Ingest</h1>
        <p className="text-sm text-muted-foreground">Add a paper or an article. The new pages come back as a proposal you review.</p>
      </header>
      {wizard ? <WizardLayout flow={flow} /> : <SingleLayout flow={flow} />}
    </div>
  );
}

function IngestHealth() {
  const health = useApiQuery(["health"], (d) => d.getHealth(), { staleTime: 60_000 });
  return <HealthView health={health.data as HealthLike | undefined} error={health.error} onRetry={() => void health.refetch()} />;
}

/**
 * /ingest (flag ui.ingest). With ui.data-system-split Ingest owns the data: tabs Overview (tiles, Add, Data issues, Recent data changes),
 * Pipeline, Health and History, the screens System hosted before, reused as they are. Flag off: the add flow alone.
 */
export default function IngestScreen() {
  const split = useFlag("ui.data-system-split");
  const search = useSearch({ strict: false }) as SearchById["ingest"];
  const navigate = useNavigate();
  if (!split) return <AddFlow />;
  const tab: IngestTab = search.tab && INGEST_TABS.includes(search.tab) ? search.tab : "overview";
  const open = (t: IngestTab) => void navigate({ to: ".", search: { tab: t === "overview" ? undefined : t } as never });
  return (
    <div className="flex flex-col gap-4">
      <div className="flex gap-1 border-b" role="tablist" aria-label="Ingest sections">
        {INGEST_TABS.map((t) => (
          <button
            key={t}
            role="tab"
            aria-selected={tab === t}
            onClick={() => open(t)}
            className="-mb-px border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground hover:text-foreground aria-selected:border-primary aria-selected:text-foreground"
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>
      {tab === "overview" && <IngestOverview add={<AddBody />} onOpen={open} />}
      {tab === "pipeline" && <PipelineScreen />}
      {tab === "health" && <IngestHealth />}
      {tab === "history" && <LifecycleScreen />}
    </div>
  );
}
