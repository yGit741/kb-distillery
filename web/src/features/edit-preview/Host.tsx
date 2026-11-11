import { useEffect } from "react";
import { useDataSource } from "@/api";
import { fileProblem } from "@/features/ingest/model";
import { useFlag } from "@/flags/useFlag";
import { PlanSheet } from "./Plan";
import { EditPreviewSheet } from "./Sheet";
import { useEditPreview } from "./store";

const hasFiles = (e: DragEvent) => !!e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files");
/** `?preview=sample` opens the sample sheet; any other value is a proposal id and opens its plan. */
const SAMPLE = "sample";

/**
 * Mounts the edit preview on the graph (flag ui.edit-preview). A file dropped anywhere on the graph opens the pop-up
 * straight away: with ui.ingest on the file is read for real (always deep) and its proposal arrives as a plan graph;
 * without it the sample sheet plays. `?preview=<proposal id>` opens that proposal's plan. A drop that another
 * control took (the add-sources card) is left alone.
 */
export function EditPreviewHost({ preview }: { preview?: string }) {
  return useFlag("ui.edit-preview") ? <Mounted preview={preview} /> : null;
}

function Mounted({ preview }: { preview?: string }) {
  const real = useFlag("ui.ingest");
  const show = useEditPreview((s) => s.show);
  const showPlan = useEditPreview((s) => s.showPlan);
  useEffect(() => {
    if (preview === SAMPLE) show();
    else if (preview) showPlan({ proposalId: preview });
  }, [preview, show, showPlan]);
  return (
    <>
      {real ? <RealDrop /> : <SampleDrop />}
      <EditPreviewSheet />
      <PlanSheet />
    </>
  );
}

/** Listens for a file dropped on the window; `onFile` gets the first file of a drop nobody else took. */
function useWindowDrop(onFile: (f: File | undefined) => void) {
  useEffect(() => {
    const over = (e: DragEvent) => {
      if (hasFiles(e) && !e.defaultPrevented) e.preventDefault();
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e) || e.defaultPrevented) return;
      e.preventDefault();
      onFile(e.dataTransfer?.files?.[0]);
    };
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [onFile]);
}

function SampleDrop() {
  const show = useEditPreview((s) => s.show);
  useWindowDrop(() => {
    // a second file while the sheet is up does not restart the reading
    if (!useEditPreview.getState().open) show({ reading: true });
  });
  return null;
}

/** One dropped source is always read deep; the job's proposal becomes the plan on screen. */
function RealDrop() {
  const ds = useDataSource();
  const showPlan = useEditPreview((s) => s.showPlan);
  useWindowDrop((file) => {
    if (!file || useEditPreview.getState().plan) return;
    const problem = fileProblem(file);
    if (problem) return showPlan({ name: file.name, error: problem });
    showPlan({ name: file.name });
    ds.startIngest({ file, tier: "deep" }).then(
      (started) => showPlan({ name: file.name, jobId: started.job_id }),
      (e: unknown) => showPlan({ name: file.name, error: e instanceof Error ? e.message : "Could not start reading this file." }),
    );
  });
  return null;
}
