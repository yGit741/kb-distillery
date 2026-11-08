import { Lock } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { NEEDS_CLAUDE } from "./status";

/** Calm mark for agent controls that cannot run: the control stays, the reason is one hover (and one 409) away. */
export function NeedsClaudeBadge({ reason }: { reason?: string }) {
  return (
    <Badge variant="outline" title={reason || undefined} data-testid="needs-claude">
      <Lock aria-hidden className="mr-1 size-3" />
      {NEEDS_CLAUDE}
    </Badge>
  );
}
