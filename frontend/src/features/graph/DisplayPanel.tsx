import { CheckField, RangeField, SelectField } from "./controls";
import { LABEL_MODES, type LabelField } from "./labels";
import { useGraphUi } from "./store";
import { COLOR_BY, SIZE_BY } from "./style";

const FIELDS: readonly { id: LabelField; label: string }[] = [
  { id: "title", label: "Title" },
  { id: "slug", label: "Slug" },
];

export function DisplayPanel() {
  const ui = useGraphUi();
  return (
    <div className="flex flex-col gap-3">
      <SelectField label="Show labels for" value={ui.labelMode} options={LABEL_MODES} onChange={(labelMode) => ui.set({ labelMode })} />
      <SelectField label="Label text" value={ui.labelField} options={FIELDS} onChange={(labelField) => ui.set({ labelField })} />
      <SelectField label="Colour by" value={ui.colorBy} options={COLOR_BY} onChange={(colorBy) => ui.set({ colorBy })} />
      <SelectField label="Size by" value={ui.sizeBy} options={SIZE_BY} onChange={(sizeBy) => ui.set({ sizeBy })} />
      <RangeField label="Base size" value={ui.nodeSize} min={2} max={12} step={0.5} onChange={(nodeSize) => ui.set({ nodeSize })} />
      <RangeField label="Link opacity" value={ui.linkOpacity} min={0.05} max={0.9} step={0.05} onChange={(linkOpacity) => ui.set({ linkOpacity })} />
      <CheckField label="Directional arrows" checked={ui.arrows} onChange={(arrows) => ui.set({ arrows })} />
      <CheckField label="Highlight neighbourhood" checked={ui.highlight} onChange={(highlight) => ui.set({ highlight })} hint="Dim everything but the hovered or selected pages and their neighbours" />
      <CheckField label="Magnetic pointer" checked={ui.magnet} onChange={(magnet) => ui.set({ magnet })} hint="Hover takes the nearest page; how far it reaches follows how crowded the graph is around it" />
    </div>
  );
}
