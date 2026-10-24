import type { Depth } from "@/api/model";
import { DEPTH_COLORS, PILE_COLORS, STATUS_COLORS, UNKNOWN_COLOR } from "@/theme/palette";
import { STATUS_LABEL, STATUS_TIP, type Status } from "./items";

/** Colour of a pipeline status dot; digested units take their depth colour. All values come from the palette. */
export function statusColor(status: Status, depth: Depth | "" = ""): string | undefined {
  switch (status) {
    case "inbox": return STATUS_COLORS.reading;
    case "failed": return undefined; // drawn with the chrome `bad` token
    case "uncataloged": return STATUS_COLORS.open;
    case "undigested": return STATUS_COLORS["to-read"];
    case "partial": return STATUS_COLORS.partial;
    case "digested": return depth ? DEPTH_COLORS[depth] : STATUS_COLORS.digested;
    case "skipped": return STATUS_COLORS.archived;
  }
}

export const formatColor = (format: string): string =>
  (PILE_COLORS as Record<string, string>)[format] ?? UNKNOWN_COLOR;

export function Dot({ color, className = "" }: { color?: string; className?: string }) {
  return (
    <span
      aria-hidden
      className={`inline-block size-2 shrink-0 rounded-full ${color ? "" : "bg-bad"} ${className}`}
      style={color ? { background: color } : undefined}
    />
  );
}

export function StatusPill({ status, depth = "" }: { status: Status; depth?: Depth | "" }) {
  const label = status === "digested" && depth ? `digested · ${depth}` : STATUS_LABEL[status];
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs" title={STATUS_TIP[status]}>
      <Dot color={statusColor(status, depth)} />
      {label}
    </span>
  );
}
