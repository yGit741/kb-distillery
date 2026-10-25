import { afterEach, describe, expect, it } from "vitest";
import { FLAGS, FLAG_ENV, FLAG_NAMES, flag, flagIn, setFlagOverrides, type FlagName } from "./index";

afterEach(() => setFlagOverrides({}));

describe("flag()", () => {
  it("the test bundle runs as the local app", () => expect(FLAG_ENV).toBe("local"));
  it("resolves the local value of every flag", () => {
    for (const n of FLAG_NAMES) expect(flag(n)).toBe(FLAGS[n].envs.local);
  });
  it("per-env values come from the registry", () => {
    expect(flagIn("screen.share", "local")).toBe(false);
    expect(flagIn("screen.share", "private")).toBe(true);
    expect(flagIn("screen.share", "public")).toBe(false);
    expect(flagIn("screen.lifecycle", "local")).toBe(true);
    expect(flagIn("screen.lifecycle", "public")).toBe(false);
  });
  it("unknown names are off", () => expect(flag("nope" as FlagName)).toBe(false));
  it("overrides never change build flags", () => {
    setFlagOverrides({ "screen.share": true });
    expect(FLAGS["screen.share"].kind).toBe("build");
    expect(flag("screen.share")).toBe(false);
  });
});
