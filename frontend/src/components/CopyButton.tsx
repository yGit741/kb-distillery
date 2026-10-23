import { useState } from "react";
import { Button } from "@/components/ui/button";

/** Copies `text`; if the clipboard is blocked, shows the text so it can be copied by hand. */
export function CopyButton({ text, label = "Copy" }: { text: string; label?: string }) {
  const [state, setState] = useState<"idle" | "copied" | "manual">("idle");
  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setState("copied");
    } catch {
      setState("manual");
    }
    setTimeout(() => setState("idle"), 1500);
  };
  return (
    <Button variant="secondary" size="sm" onClick={onClick} title={text}>
      {state === "copied" ? "Copied" : state === "manual" ? text : label}
    </Button>
  );
}
