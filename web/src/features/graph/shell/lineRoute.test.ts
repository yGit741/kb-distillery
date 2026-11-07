import { closestCommands, commandScore, MIN_CLOSEST, type Command } from "./commands";
import { readsAsQuestion, readsAsView, routeByRules, strongCommand } from "./lineRoute";

const cmd = (id: string, label: string): Command => ({ id, label, group: "View", icon: "fit", run: () => {} });
const COMMANDS = [cmd("fit", "Fit to view"), cmd("zoom-in", "Zoom in"), cmd("zoom-out", "Zoom out"), cmd("filters", "Filters"), cmd("refresh", "Refresh graph")];
const PAGES = [
  { id: "topic-learning-theory", title: "Learning theory" },
  { id: "idea-margin", title: "Margin" },
  { id: "2019-long", title: "A long title about margin bounds in 2019" },
];
const ctx = { pages: PAGES, commands: COMMANDS, canAsk: true };

describe("routeByRules: one row per intent", () => {
  it.each([
    ["Learning theory", "search", "topic-learning-theory"],
    ["idea-margin", "search", "idea-margin"],
    ["learning", "search", undefined],
    ["a long title about margin bounds", "search", undefined],
    ["tensor rank", "search", undefined],
    ["filter out all jane doe blogs that are with degree 1", "view", undefined],
    ["show only papers", "view", undefined],
    ["hide blog posts", "view", undefined],
    ["colour by area", "view", undefined],
    ["papers without links", "view", undefined],
    ["group by type", "view", undefined],
    ["what connects margin and compression", "ask", undefined],
    ["explain the margin bound", "ask", undefined],
    ["is margin related to compression?", "ask", undefined],
    ["zoom out", "command", "zoom-out"],
    ["zom out", "command", "zoom-out"],
    ["filters", "command", "filters"],
  ])("%s -> %s", (text, intent, id) => {
    expect(routeByRules(text, ctx)).toEqual({ intent, text, ...(id ? { id } : {}) });
  });

  it("a long line none of the rules place goes to the model (null)", () => {
    expect(routeByRules("the thing jane doe wrote about noise last spring", ctx)).toBeNull();
  });

  it("an exact title wins over view words and question words", () => {
    const pages = [{ id: "q-why-hide", title: "Why hide layers" }];
    expect(routeByRules("why hide layers", { ...ctx, pages })).toEqual({ intent: "search", text: "why hide layers", id: "q-why-hide" });
  });

  it("without the chat a question is not sent there", () => {
    expect(routeByRules("why do big nets work?", { ...ctx, canAsk: false })).toBeNull();
    expect(routeByRules("why nets?", { ...ctx, canAsk: false })).toEqual({ intent: "search", text: "why nets?" });
  });

  it("empty text is not routed", () => {
    expect(routeByRules("   ", ctx)).toBeNull();
  });
});

describe("the words behind the rules", () => {
  it("view words, question words", () => {
    expect(readsAsView("remove orphans")).toBe(true);
    expect(readsAsView("size by links")).toBe(true);
    expect(readsAsView("tensor rank")).toBe(false);
    expect(readsAsQuestion("how do margins work")).toBe(true);
    expect(readsAsQuestion("margin bounds")).toBe(false);
  });
});

describe("command scores and the junk threshold", () => {
  it("a full name scores 1, a sentence that shares a word scores near 0", () => {
    expect(commandScore(cmd("zoom-out", "Zoom out"), "zoom out")).toBe(1);
    expect(commandScore(cmd("zoom-out", "Zoom out"), "filter out all jane doe blogs that are with degree 1")).toBeLessThan(MIN_CLOSEST);
    expect(commandScore(cmd("filters", "Filters"), "filter out all jane doe blogs that are with degree 1")).toBeLessThan(MIN_CLOSEST);
  });

  it("closest options under the threshold are not offered; a typo still is", () => {
    const sentence = "filter out all jane doe blogs that are with degree 1";
    expect(closestCommands(COMMANDS, sentence).length).toBe(3);
    expect(closestCommands(COMMANDS, sentence, 3, MIN_CLOSEST)).toEqual([]);
    expect(closestCommands(COMMANDS, "zom", 3, MIN_CLOSEST).map((c) => c.id)).toEqual(expect.arrayContaining(["zoom-in", "zoom-out"]));
  });

  it("a strong command needs most of its words", () => {
    expect(strongCommand(COMMANDS, "refresh")).toBeUndefined();
    expect(strongCommand(COMMANDS, "refresh graph")?.id).toBe("refresh");
    expect(strongCommand(COMMANDS, "fit")).toBeUndefined();
  });
});
