import { Command as Cmdk } from "cmdk";
import { Search } from "lucide-react";
import type { ComponentProps } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./dialog";
import { cn } from "@/lib/utils";

export const Command = ({ className, ...p }: ComponentProps<typeof Cmdk>) => (
  <Cmdk className={cn("flex w-full flex-col overflow-hidden", className)} {...p} />
);

export function CommandDialog({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent aria-describedby="cmd-desc">
        <DialogTitle className="sr-only">{title}</DialogTitle>
        <DialogDescription id="cmd-desc" className="sr-only">
          Type to filter, arrow keys to move, Enter to go.
        </DialogDescription>
        <Command>{children}</Command>
      </DialogContent>
    </Dialog>
  );
}

export const CommandInput = ({ className, ...p }: ComponentProps<typeof Cmdk.Input>) => (
  <div className="flex items-center gap-2 border-b px-3">
    <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
    <Cmdk.Input
      className={cn("h-11 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground", className)}
      {...p}
    />
  </div>
);

export const CommandList = ({ className, ...p }: ComponentProps<typeof Cmdk.List>) => (
  <Cmdk.List className={cn("max-h-80 overflow-y-auto p-1", className)} {...p} />
);
export const CommandEmpty = (p: ComponentProps<typeof Cmdk.Empty>) => (
  <Cmdk.Empty className="py-6 text-center text-sm text-muted-foreground" {...p} />
);
export const CommandGroup = ({ className, ...p }: ComponentProps<typeof Cmdk.Group>) => (
  <Cmdk.Group
    className={cn(
      "[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-muted-foreground",
      className,
    )}
    {...p}
  />
);
export const CommandItem = ({ className, ...p }: ComponentProps<typeof Cmdk.Item>) => (
  <Cmdk.Item
    className={cn(
      "flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 text-sm data-[selected=true]:bg-accent",
      className,
    )}
    {...p}
  />
);
