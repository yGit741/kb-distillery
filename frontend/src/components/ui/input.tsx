import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const Input = ({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) => (
  <input
    className={cn(
      "h-9 w-full rounded-md border bg-transparent px-3 text-sm placeholder:text-muted-foreground",
      className,
    )}
    {...p}
  />
);
