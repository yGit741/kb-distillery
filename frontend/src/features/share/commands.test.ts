import type { TimelineRow } from "@/api";
import { snapshotCommand, validName, versionOptions } from "./commands";

const row = (o: Partial<TimelineRow>): TimelineRow =>
  ({ sha: "a", short: "a", date: "2026-10-23T10:00:00+00:00", subject: "s", kind: "kb", kb_version: null, summary: null, ...o }) as TimelineRow;

describe("commands", () => {
  it("validates names", () => {
    expect(validName("cohen")).toBe(true);
    expect(validName("a-b")).toBe(true);
    expect(validName("-a")).toBe(false);
    expect(validName("kb")).toBe(false);
    expect(validName("Up")).toBe(false);
  });
  it("builds the CLI command, with --replace", () => {
    expect(snapshotCommand("Cohen", "kb-1.0.3", false)).toBe("pixi run share -- snapshot cohen kb-1.0.3");
    expect(snapshotCommand("", "", true)).toBe("pixi run share -- snapshot <name> <version> --replace");
  });
  it("lists knowledge steps only", () => {
    const o = versionOptions([row({ kb_version: "1.0.3", summary: "did x" }), row({ kind: "pr-merge" }), row({ kb_version: "1.0.2" })]);
    expect(o.map((x) => x.tag)).toEqual(["kb-1.0.3", "kb-1.0.2"]);
    expect(o[0]!.date).toBe("2026-10-23");
  });
});
