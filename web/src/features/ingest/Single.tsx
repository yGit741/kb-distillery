import { IngestInbox } from "./Inbox";
import { SourcePicker, TriageCard } from "./parts";
import { useCollections, type Flow } from "./model";

/**
 * Variant `single`: the form on top (the drop zone, then the triage card once a source is chosen) and under it the
 * inbox of everything brought in. Starting an ingest adds its row to the inbox and clears the form for the next one.
 */
export function SingleLayout({ flow }: { flow: Flow }) {
  const collections = useCollections();
  return (
    <div className="flex flex-col gap-8" data-layout="single">
      {flow.source ? <TriageCard flow={flow} collections={collections} /> : <SourcePicker onSource={flow.setSource} tall />}
      <IngestInbox />
    </div>
  );
}
