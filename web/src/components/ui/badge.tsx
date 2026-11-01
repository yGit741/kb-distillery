import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap", {
  variants: {
    variant: {
      default: "bg-secondary text-secondary-foreground",
      primary: "bg-accent-soft text-primary",
      ok: "bg-ok/15 text-ok",
      warn: "bg-warn/15 text-warn",
      bad: "bg-bad/15 text-bad",
      outline: "border text-muted-foreground",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export const Badge = ({ className, variant, ...p }: BadgeProps) => (
  <span className={cn(badgeVariants({ variant }), className)} {...p} />
);
