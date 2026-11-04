import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface SwitchProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onChange" | "role"> {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

/** A plain on/off toggle. The state shows in the thumb's side as well as the track, so colour is never the only signal. */
export function Switch({ checked, onCheckedChange, className, disabled, ...p }: SwitchProps) {
  return (
    <button
      {...p}
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      className={cn(
        "relative inline-flex h-6 w-10 shrink-0 items-center rounded-full border transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-60 motion-reduce:transition-none",
        checked ? "border-primary bg-primary" : "border-muted-foreground/60 bg-muted",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "size-4 rounded-full transition-transform motion-reduce:transition-none",
          checked ? "translate-x-[1.375rem] bg-primary-foreground" : "translate-x-0.5 bg-muted-foreground",
        )}
      />
    </button>
  );
}
