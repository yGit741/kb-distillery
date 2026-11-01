import type { ReactNode, SelectHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const selectClass =
  "h-9 w-full rounded-md border bg-background px-2 text-sm disabled:opacity-60";

export function Select({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(selectClass, className)} {...p} />;
}

/** A label wrapping its control, so the control is named without ids. */
export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-muted-foreground">
      {label}
      {children}
      {hint && <span className="font-normal">{hint}</span>}
    </label>
  );
}
