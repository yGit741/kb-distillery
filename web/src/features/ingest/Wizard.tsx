import { useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { JobCard, SourcePicker, SourceSummary, TriageCard } from "./parts";
import { sourceName, useCollections, type Flow } from "./model";

const STEPS = ["Source", "What is it", "Progress"] as const;

function Stepper({ at }: { at: number }) {
  return (
    <ol className="flex items-center gap-2 text-sm" aria-label="Steps">
      {STEPS.map((s, i) => (
        <li key={s} aria-current={i === at ? "step" : undefined} className={cn("flex items-center gap-2", i === at ? "font-medium" : "text-muted-foreground")}>
          <span className={cn("grid size-5 place-items-center rounded-full border text-xs tabular-nums", i === at && "border-primary text-primary", i < at && "border-transparent bg-accent-soft text-primary")}>
            {i < at ? <Check className="size-3" strokeWidth={2} aria-hidden /> : i + 1}
          </span>
          {s}
          {i < STEPS.length - 1 && <span className="mx-1 h-px w-8 bg-border" aria-hidden />}
        </li>
      ))}
    </ol>
  );
}

/** Variant `wizard`: one narrow column, three steps shown one at a time. Starting the job moves to the last step. */
export function WizardLayout({ flow }: { flow: Flow }) {
  const collections = useCollections();
  const [step, setStep] = useState(0);
  const at = flow.jobId ? 2 : step;
  return (
    <div className="flex flex-col gap-5" data-layout="wizard">
      <Stepper at={at} />
      {at === 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Choose a source</CardTitle>
            <CardDescription>A paper, an article or a web page.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            {flow.source ? <SourceSummary source={flow.source} onChange={() => flow.setSource(null)} /> : <SourcePicker onSource={flow.setSource} />}
            <Button className="self-end" disabled={!flow.source} onClick={() => setStep(1)}>Next</Button>
          </CardContent>
        </Card>
      )}
      {at === 1 && (
        <TriageCard flow={flow} collections={collections} onBack={() => setStep(0)} />
      )}
      {at === 2 && (
        <JobCard job={flow.job} source={flow.source ? sourceName(flow.source) : ""} started onAgain={() => { flow.reset(); setStep(0); }} />
      )}
    </div>
  );
}
