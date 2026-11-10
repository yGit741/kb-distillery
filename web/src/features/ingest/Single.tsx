import { JobCard, SourcePicker, TriageCard } from "./parts";
import { sourceName, useCollections, type Flow } from "./model";

/**
 * Variant `single`: two columns on one page. The left column is the drop zone, then the triage card once a source is
 * chosen; the right column always holds the progress card (idle until the job starts), so nothing jumps when it begins.
 */
export function SingleLayout({ flow }: { flow: Flow }) {
  const collections = useCollections();
  const started = flow.jobId !== null;
  return (
    <div className="grid items-start gap-6 md:grid-cols-[minmax(0,1fr)_20rem]" data-layout="single">
      <div className="flex min-w-0 flex-col gap-4">
        {flow.source ? <TriageCard flow={flow} collections={collections} /> : <SourcePicker onSource={flow.setSource} tall />}
      </div>
      <div className="md:sticky md:top-4">
        <JobCard job={flow.job} source={flow.source ? sourceName(flow.source) : ""} started={started} onAgain={flow.reset} />
      </div>
    </div>
  );
}
