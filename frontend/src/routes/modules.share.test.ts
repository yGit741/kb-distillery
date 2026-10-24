import { describe, expect, it } from "vitest";
import { modules as all } from "./modules";
import { modules as priv } from "./modules.share-private";
import { modules as pub } from "./modules.share-public";

const ids = (m: Record<string, unknown>) =>
  Object.keys(m).map((f) => /features\/([^/]+)\/index\.tsx$/.exec(f)![1]!).sort();

/** Build-time route inclusion: the share builds import a literal list, never the chat / ops / scopes screens. */
describe("share route modules", () => {
  it("public = home + graph + pages", () => expect(ids(pub)).toEqual(["graph", "home", "pages"]));
  it("private = home + graph + pages + lifecycle + share", () => expect(ids(priv)).toEqual(["graph", "home", "lifecycle", "pages", "share"]));
  it("the full app still has every screen", () => {
    expect(ids(all)).toEqual(expect.arrayContaining(["chat", "graph", "lifecycle", "pages", "pipeline", "scopes"]));
  });
  it("no excluded screen is reachable from either share list", () => {
    for (const bad of ["chat", "scopes", "pipeline", "ops", "system", "legacy"]) {
      expect(ids(pub)).not.toContain(bad);
      expect(ids(priv)).not.toContain(bad);
    }
  });
});
