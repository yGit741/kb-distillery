import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { components } from "@/api/schema";
import { isParseError, parse, print } from "./grammar";
import { describe as words, evaluate, type Layer, type ViewStack } from "./model";

/**
 * The layer objects the server validates (src/kb_distillery/server/models/layers.py) are the ones this model holds.
 * tests/fixtures/layers/*.json is read by pytest and by this file: the same stack must print the same lines, and the
 * generated API types must be assignable to the model the app uses (a field renamed on one side fails `tsc` here).
 */
type Api = components["schemas"];
/** Optional fields come through the API as `x?: T | null`; the model writes them `x?: T`. */
type NoNull<T> = T extends null ? never : T extends (infer U)[] ? NoNull<U>[] : T extends object ? { [K in keyof T]: NoNull<T[K]> } : T;

// compile-time: what the API sends is a Layer the store accepts (conditions, styles, targets, in both senses)
const fromApi = (l: NoNull<Api["Layer"]>): Omit<Layer, "legacy"> => l;
const toApi = (l: Omit<Layer, "legacy">): NoNull<Api["Layer"]> => l;
void [fromApi, toApi];

const dir = join(__dirname, "../../../../../tests/fixtures/layers");
const fixtures = readdirSync(dir)
  .filter((f) => f.endsWith(".json"))
  .map((f) => ({ file: f, ...(JSON.parse(readFileSync(join(dir, f), "utf8")) as { stack: ViewStack; lines: string[] }) }));

describe("layer fixtures shared with the server", () => {
  it("has fixtures", () => expect(fixtures.length).toBeGreaterThanOrEqual(2));

  for (const fx of fixtures) {
    describe(fx.file, () => {
      it("prints the lines the Python printer prints", () => expect(fx.stack.layers.map(print)).toEqual(fx.lines));

      it("reads each line back into the same conditions and style (sentence to layers to sentence)", () => {
        fx.stack.layers.forEach((layer, i) => {
          const back = parse(fx.lines[i]!);
          if (isParseError(back)) throw new Error(`${fx.lines[i]}: ${back.error}`);
          expect(back.kind).toBe(layer.kind);
          expect(back.target).toBe(layer.target);
          expect(back.subgraph).toEqual(layer.subgraph);
          expect(back.style ?? {}).toEqual(layer.style ?? {});
        });
      });

      it("describes and evaluates without throwing", () => {
        fx.stack.layers.forEach((l) => expect(words(l).length).toBeGreaterThan(0));
        expect(evaluate(fx.stack, { nodes: [], links: [] }).legend).toBeDefined();
      });
    });
  }
});
