import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export const Skeleton = ({ className, ...p }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("animate-pulse rounded-md bg-muted", className)} {...p} />
);
