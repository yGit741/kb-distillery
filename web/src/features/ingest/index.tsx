import { cn } from "@/lib/utils";
import { useVariant } from "@/components/variants";
import { useIngestFlow } from "./model";
import { SingleLayout } from "./Single";
import { WizardLayout } from "./Wizard";

/** /ingest (flag ui.ingest): drop a source, say what it is, watch the job, review the proposal. Layout is the `ingest-layout` variant. */
export default function IngestScreen() {
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
