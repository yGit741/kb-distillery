import { Activity, Compass, FlaskConical, Sigma, Waves } from "lucide-react";
import { registerTool } from "../tools";
import { EXPERIMENTS, registerExperiment, useExperiments } from "../tools/experiments";
import { DirectionsPanel } from "./DirectionsPanel";
import { FourierPanel } from "./FourierPanel";
import { NoisePanel } from "./NoisePanel";
import { ThresholdPanel } from "./ThresholdPanel";

/**
 * The Kalai toolkit: three analyses of the vault graph, each behind its own experiment flag. The
 * Experiments panel (always in the toolbar) is where they are switched on; see ./README.md.
 */
registerExperiment({
  id: "fourier",
  label: "Theme spectrum (Fourier)",
  story: "When I choose where to dig, I want to see which themes my notes combine, which big ones never meet, and what predicts my deep reading, so that I can spot a thesis at an unexplored intersection.",
  read: "Heatmap cells: blue = together more than chance, red = less. Gaps list big pairs that (almost) never share a page.",
});
registerExperiment({
  id: "noise",
  label: "Noise stability",
  story: "Before I rely on 'these ideas belong together' or 'this concept is central', I want to know whether that survives if I had missed some papers or links, so that I only argue from conclusions that are noise-stable.",
  read: "A halo marks a page whose cluster changes under the noise; the brighter, the less stable.",
});
registerExperiment({
  id: "threshold",
  label: "Sharp thresholds",
  story: "When I want to know how well a theme is woven into my vault, I want to see at what link density it holds together and which single link tips it, so that I know where one more paper or note would matter most.",
  read: "Drag p or press play: links fade out above p. A late, wide transition means the theme hangs on a few bridges.",
});
registerExperiment({
  id: "directions",
  label: "Research directions",
  story: "When I choose my thesis topic, I want the empty intersections of my vault as cards, each with what already sits there and my closest questions and ideas, so that I can shortlist directions with evidence rather than gut feeling.",
  read: "Strong foothold = my own questions already reach every side; greenfield = new ground, cold start. 'Show on graph' lights the card's pages.",
});

function ExperimentsPanel() {
  const on = useExperiments((s) => s.on);
  const toggle = useExperiments((s) => s.toggle);
  return (
    <div className="flex flex-col gap-3 text-xs">
      <p className="text-muted-foreground">
        Prototypes to try and judge. Each one adds a button to this toolbar while it is on; switches are kept in this browser only. Share a setup with{" "}
        <code>?exp=fourier,noise,threshold</code>.
      </p>
      {EXPERIMENTS.map((e) => (
        <label key={e.id} className="flex cursor-pointer gap-2 rounded-md border p-2 has-[:checked]:border-primary">
          <input type="checkbox" className="mt-0.5 accent-[var(--primary)]" checked={on.has(e.id)} onChange={() => toggle(e.id)} />
          <span className="flex flex-col gap-1">
            <span className="font-semibold">{e.label}</span>
            <span className="text-muted-foreground">{e.story}</span>
            <span className="text-muted-foreground italic">{e.read}</span>
          </span>
        </label>
      ))}
    </div>
  );
}

registerTool({
  id: "experiments",
  label: "Experiments",
  icon: <FlaskConical aria-hidden />,
  panel: () => <ExperimentsPanel />,
});

registerTool({
  id: "kalai-fourier",
  label: "Theme spectrum",
  icon: <Sigma aria-hidden />,
  flag: "fourier",
  panel: (ctx) => <FourierPanel ctx={ctx} />,
});

registerTool({
  id: "kalai-noise",
  label: "Noise stability",
  icon: <Waves aria-hidden />,
  flag: "noise",
  panel: (ctx) => <NoisePanel ctx={ctx} />,
});

registerTool({
  id: "kalai-threshold",
  label: "Sharp thresholds",
  icon: <Activity aria-hidden />,
  flag: "threshold",
  panel: (ctx) => <ThresholdPanel ctx={ctx} />,
});

registerTool({
  id: "kalai-directions",
  label: "Research directions",
  icon: <Compass aria-hidden />,
  flag: "directions",
  panel: (ctx) => <DirectionsPanel ctx={ctx} />,
});
