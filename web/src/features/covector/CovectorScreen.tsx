import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useTheme } from "@/theme/theme";
import { readouts, SIZE, slices, toCanvas, type Inputs } from "./math";

type Key = keyof Inputs;

/** The four sliders, in the order the picture explains them: first the covector generator v, then the test vector u. */
const GROUPS: { title: string; help: string; keys: { key: Key; label: string }[] }[] = [
  {
    title: "1. Covector Generator (v)",
    help: "This creates the measurement grid.",
    keys: [{ key: "vx", label: "v_x" }, { key: "vy", label: "v_y" }],
  },
  {
    title: "2. Test Vector (u)",
    help: "This is the arrow we are evaluating.",
    keys: [{ key: "ux", label: "u_x" }, { key: "uy", label: "u_y" }],
  },
];

const START: Inputs = { vx: 3, vy: 4, ux: 2, uy: 1 };

/** Theme colours for the canvas, read from the CSS variables so the picture follows light and dark. */
function palette() {
  const css = getComputedStyle(document.documentElement);
  const get = (name: string) => css.getPropertyValue(name).trim() || "currentColor";
  return { axes: get("--border"), kernel: get("--muted-foreground"), u: get("--foreground"), v: get("--primary") };
}

function arrow(ctx: CanvasRenderingContext2D, from: [number, number], to: [number, number], color: string, width: number) {
  const head = 10;
  const angle = Math.atan2(to[1] - from[1], to[0] - from[0]);
  ctx.beginPath();
  ctx.moveTo(...from);
  ctx.lineTo(...to);
  ctx.lineTo(to[0] - head * Math.cos(angle - Math.PI / 6), to[1] - head * Math.sin(angle - Math.PI / 6));
  ctx.moveTo(...to);
  ctx.lineTo(to[0] - head * Math.cos(angle + Math.PI / 6), to[1] - head * Math.sin(angle + Math.PI / 6));
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.stroke();
}

export function draw(ctx: CanvasRenderingContext2D, i: Inputs, colors = palette()) {
  const c = SIZE / 2;
  ctx.clearRect(0, 0, SIZE, SIZE);

  // axes
  ctx.beginPath();
  ctx.strokeStyle = colors.axes;
  ctx.lineWidth = 1;
  ctx.moveTo(0, c);
  ctx.lineTo(SIZE, c);
  ctx.moveTo(c, 0);
  ctx.lineTo(c, SIZE);
  ctx.stroke();

  // level sets of the covector; k = 0 is the kernel, thicker and dashed
  for (const s of slices(i)) {
    ctx.beginPath();
    ctx.strokeStyle = colors.kernel;
    ctx.globalAlpha = s.k === 0 ? 0.9 : 0.35;
    ctx.lineWidth = s.k === 0 ? 2 : 1;
    ctx.setLineDash(s.k === 0 ? [5, 5] : []);
    ctx.moveTo(...s.from);
    ctx.lineTo(...s.to);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;
  ctx.setLineDash([]);

  const origin = toCanvas(0, 0);
  const u = toCanvas(i.ux, i.uy);
  arrow(ctx, origin, u, colors.u, 3);
  arrow(ctx, origin, toCanvas(i.vx, i.vy), colors.v, 4);

  // a dot at the tip of u shows where it lands on the grid
  ctx.beginPath();
  ctx.arc(u[0], u[1], 5, 0, 2 * Math.PI);
  ctx.fillStyle = colors.u;
  ctx.fill();
}

export function CovectorScreen() {
  const [inputs, setInputs] = useState<Inputs>(START);
  const canvas = useRef<HTMLCanvasElement>(null);
  const theme = useTheme((s) => s.theme);
  const out = readouts(inputs);

  useEffect(() => {
    const ctx = canvas.current?.getContext("2d");
    if (ctx) draw(ctx, inputs);
  }, [inputs, theme]);

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Covector Visualization</h1>
      </div>
      <div className="flex flex-wrap items-start gap-5">
        <Card className="w-full sm:w-80">
          <CardContent className="flex flex-col gap-4 p-5">
            {GROUPS.map((g) => (
              <section key={g.title} aria-label={g.title} className="flex flex-col gap-2">
                <CardHeader className="p-0">
                  <CardTitle className="text-base">{g.title}</CardTitle>
                  <CardDescription>{g.help}</CardDescription>
                </CardHeader>
                <div className="flex flex-col gap-3 rounded-lg border bg-muted/40 p-3">
                  {g.keys.map(({ key, label }) => (
                    <div key={key}>
                      <label htmlFor={key} className="mb-1 block text-sm font-medium">
                        {label}: <span data-testid={`${key}-val`}>{inputs[key].toFixed(1)}</span>
                      </label>
                      <input
                        id={key}
                        type="range"
                        min={-5}
                        max={5}
                        step={0.1}
                        value={inputs[key]}
                        onChange={(e) => setInputs((p) => ({ ...p, [key]: parseFloat(e.target.value) }))}
                        className="w-full accent-primary"
                      />
                    </div>
                  ))}
                </div>
              </section>
            ))}
            <div className="rounded-lg bg-muted p-4 text-sm" aria-label="Readouts">
              <div>
                Generator Length ||v||: <b data-testid="v-len" className="text-primary">{out.vLen}</b>
              </div>
              <div>
                Grid Spacing (d): <b data-testid="spacing" className="text-primary">{out.spacing}</b> units
              </div>
              <div className="mt-2">
                Score k = ω(u): <b data-testid="score" className="text-base">{out.score}</b>
              </div>
            </div>
          </CardContent>
        </Card>
        <canvas
          ref={canvas}
          width={SIZE}
          height={SIZE}
          aria-label="Covector picture: level lines of v and the test vector u"
          className="h-auto max-w-full rounded-xl border bg-card shadow-[var(--shadow)]"
        />
      </div>
    </div>
  );
}
