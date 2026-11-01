import type { Usage } from "./sse";

export const fmtNum = (x: number | undefined) => (x || 0).toLocaleString("en-US");

export const fmtUsd = (x: number | undefined) => {
  const v = x || 0;
  return v >= 1 ? `$${v.toFixed(2)}` : v >= 0.01 ? `$${v.toFixed(3)}` : `$${v.toFixed(4)}`;
};

/** "1,200 in · 300 cached · 80 out · $0.012" (subscription turns show the API-price estimate instead). */
export function tokenLine(u: Usage | undefined): string {
  if (!u) return "";
  const input = (u.input_tokens || 0) + (u.cache_read_input_tokens || 0) + (u.cache_creation_input_tokens || 0);
  const parts = [`${fmtNum(input)} in`];
  if (u.cache_read_input_tokens) parts.push(`${fmtNum(u.cache_read_input_tokens)} cached`);
  parts.push(`${fmtNum(u.output_tokens)} out`);
  if (u.billing === "subscription") {
    parts.push(`subscription${typeof u.est_cost_usd === "number" ? ` (about ${fmtUsd(u.est_cost_usd)} at API prices)` : ""}`);
  } else if (typeof u.cost_usd === "number") parts.push(fmtUsd(u.cost_usd));
  return parts.join(" · ");
}
