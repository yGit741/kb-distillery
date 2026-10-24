import { useEffect, useRef, type ReactNode } from "react";
import { create } from "zustand";
import { areaColor } from "@/theme/palette";
import type { GraphModel } from "../types";

/**
 * Results survive closing a panel: each experiment caches its last result with the model and options that
 * produced it, and recomputes only when either changes.
 */
interface Cached<T> {
  model: GraphModel | null;
  key: string;
  value: T | null;
}

interface CacheState {
  slots: Record<string, Cached<unknown>>;
  put: (slot: string, c: Cached<unknown>) => void;
}

export const useKalaiCache = create<CacheState>((set) => ({
  slots: {},
  put: (slot, c) => set((s) => ({ slots: { ...s.slots, [slot]: c } })),
}));

export function useCached<T>(slot: string, model: GraphModel, key: string): T | null {
  const c = useKalaiCache((s) => s.slots[slot]);
  return c && c.model === model && c.key === key ? (c.value as T) : null;
}

/** Short theme names for tight places: "implicit-regularization" -> "implicit reg." */
export function shortTheme(t: string): string {
  const words = t.split("-");
  if (t.length <= 12) return words.join(" ");
  return words.length > 1 ? `${words[0]} ${(words[1] ?? "").slice(0, 3)}.` : `${t.slice(0, 10)}.`;
}

export function ThemeChip({ theme, onClick }: { theme: string; onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick} className="inline-flex items-center gap-1 rounded px-0.5 text-left hover:bg-muted" title={theme}>
      <span aria-hidden className="inline-block size-2 shrink-0 rounded-full" style={{ background: areaColor(theme) }} />
      <span>{shortTheme(theme)}</span>
    </button>
  );
}

export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-1.5">
      <h3 className="text-xs font-semibold" title={hint}>
        {title}
      </h3>
      {children}
    </section>
  );
}

export function Story({ children }: { children: ReactNode }) {
  return <p className="rounded-md bg-muted/60 p-2 text-xs text-muted-foreground">{children}</p>;
}

export const pct = (x: number): string => `${Math.round(x * 100)}%`;
export const num = (x: number, d = 2): string => (Number.isFinite(x) ? x.toFixed(d) : "never");

/** Clears this tool's canvas decor when its panel closes. */
export function useDecorLifetime(clear: () => void): void {
  const ref = useRef(clear);
  ref.current = clear;
  useEffect(() => () => ref.current(), []);
}

export interface Series {
  id: string;
  label: string;
  color: string;
  points: readonly { x: number; y: number }[];
}

/**
 * A small line chart on 0..1 x 0..1: 2px lines, a recessive frame, an optional vertical marker, hover
 * titles on each series. Colour follows the entity (a theme keeps its palette colour); ≥2 series get a
 * legend below.
 */
export function MiniChart({ series, marker, xLabel, yLabel, height = 110 }: { series: readonly Series[]; marker?: number; xLabel: string; yLabel: string; height?: number }) {
  const W = 280;
  const H = height;
  const pad = { l: 26, r: 6, t: 6, b: 18 };
  const x = (v: number) => pad.l + v * (W - pad.l - pad.r);
  const y = (v: number) => H - pad.b - v * (H - pad.t - pad.b);
  return (
    <figure className="flex flex-col gap-1">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full text-muted-foreground" role="img" aria-label={`${yLabel} by ${xLabel}`}>
        {[0, 0.5, 1].map((g) => (
          <g key={g}>
            <line x1={pad.l} x2={W - pad.r} y1={y(g)} y2={y(g)} stroke="currentColor" strokeOpacity={0.15} />
            <text x={pad.l - 4} y={y(g) + 3} fontSize={8} textAnchor="end" fill="currentColor">
              {g}
            </text>
          </g>
        ))}
        {[0, 0.5, 1].map((g) => (
          <text key={g} x={x(g)} y={H - 5} fontSize={8} textAnchor="middle" fill="currentColor">
            {g}
          </text>
        ))}
        {series.map((s) => (
          <polyline key={s.id} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" points={s.points.map((p) => `${x(p.x)},${y(p.y)}`).join(" ")}>
            <title>{s.label}</title>
          </polyline>
        ))}
        {marker !== undefined && <line x1={x(marker)} x2={x(marker)} y1={pad.t} y2={H - pad.b} stroke="currentColor" strokeDasharray="3 2" />}
      </svg>
      <figcaption className="flex flex-wrap gap-x-2 text-[10px] text-muted-foreground">
        <span>
          x: {xLabel} · y: {yLabel}
        </span>
        {series.length > 1 &&
          series.map((s) => (
            <span key={s.id} className="inline-flex items-center gap-1">
              <span aria-hidden className="inline-block h-0.5 w-3" style={{ background: s.color }} />
              {s.label}
            </span>
          ))}
      </figcaption>
    </figure>
  );
}
