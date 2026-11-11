import { useEffect } from "react";
import { useFlag } from "@/flags/useFlag";
import { EditPreviewSheet } from "./Sheet";
import { useEditPreview } from "./store";

const hasFiles = (e: DragEvent) => !!e.dataTransfer && Array.from(e.dataTransfer.types).includes("Files");

/**
 * Mounts the edit preview on the graph (flag ui.edit-preview). A file dropped anywhere on the graph opens the
 * sheet straight away, reading; `?preview=sample` opens it on the sample item. A drop that another control took
 * (the add-sources card) is left alone.
 */
export function EditPreviewHost({ preview }: { preview?: string }) {
  return useFlag("ui.edit-preview") ? <Mounted preview={preview} /> : null;
}

function Mounted({ preview }: { preview?: string }) {
  const show = useEditPreview((s) => s.show);
  useEffect(() => {
    if (preview) show();
  }, [preview, show]);
  useEffect(() => {
    const over = (e: DragEvent) => {
      if (hasFiles(e) && !e.defaultPrevented) e.preventDefault();
    };
    const drop = (e: DragEvent) => {
      if (!hasFiles(e) || e.defaultPrevented) return;
      e.preventDefault();
      show({ reading: true });
    };
    window.addEventListener("dragover", over);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("dragover", over);
      window.removeEventListener("drop", drop);
    };
  }, [show]);
  return <EditPreviewSheet />;
}
