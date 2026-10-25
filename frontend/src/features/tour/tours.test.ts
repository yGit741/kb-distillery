import { ACTIVE_CLASS, atLocation, routesOf, startTour } from "./engine";
import { installTours, listTours, markSeen, registerTour, runTour, seenTour, type TourStep } from "./tours";

const dock = () => document.querySelector<HTMLElement>('.gt-dock[aria-label="Guided tour"]');
const nextB = () => document.querySelector<HTMLButtonElement>(".gt-dock .gt-next");
const backB = () => document.querySelector<HTMLButtonElement>(".gt-dock .gt-back");
const skipB = () => document.querySelector<HTMLButtonElement>(".gt-dock .gt-skip");
const title = () => document.querySelector(".gt-card h4")?.textContent;
const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));
const until = async (ok: () => boolean, ms = 1500) => {
  const t0 = Date.now();
  while (!ok() && Date.now() - t0 < ms) await tick(20);
};
/** a kbGo stub that moves the (jsdom) location and renders the target of the page it lands on */
function fakeGo(late = 0) {
  return vi.fn((path: string) => {
    const [p, qs = ""] = path.split("?");
    window.history.replaceState(null, "", `${p}${qs ? `?${qs}` : ""}`);
    const id = p === "/" ? "home" : "late";
    if (!document.getElementById(id)) setTimeout(() => document.body.insertAdjacentHTML("beforeend", `<div id="${id}">${id}</div>`), late);
  });
}

afterEach(() => {
  skipB()?.click(); // end a running tour
  vi.useRealTimers();
  document.body.innerHTML = "";
  localStorage.clear();
  delete window.kbGo;
  delete globalThis.KB_EMBEDDED;
  window.history.replaceState(null, "", "/");
});

describe("tour engine", () => {
  it("knows where the window is, under the app base path", () => {
    expect(atLocation("/", { pathname: "/app/", search: "" })).toBe(true);
    expect(atLocation("/", { pathname: "/", search: "" })).toBe(true);
    expect(atLocation("/graph?view=thesis", { pathname: "/app/graph", search: "?view=thesis&from=home" })).toBe(true);
    expect(atLocation("/graph?view=thesis", { pathname: "/app/graph", search: "?view=map" })).toBe(false);
    expect(atLocation("/graph", { pathname: "/app/", search: "" })).toBe(false);
  });

  it("gives every step a route: its own `go`, else the previous one, else Home", () => {
    const steps: TourStep[] = [
      { target: "a", title: "", body: "" },
      { target: "b", title: "", body: "", go: "/graph?view=map" },
      { target: "c", title: "", body: "" },
      { target: "d", title: "", body: "", go: "/" },
    ];
    expect(routesOf(steps)).toEqual(["/", "/graph?view=map", "/graph?view=map", "/"]);
  });

  it("navigates through kbGo for a `go` step, awaits the target for `wait`, and navigates back on Back", async () => {
    const kbGo = fakeGo(300);
    window.kbGo = kbGo;
    document.body.innerHTML = '<div id="home">home</div>';
    const steps: TourStep[] = [
      { target: "#home", title: "A", body: "a" },
      { target: "#late", title: "B", body: "b", go: "/graph?view=thesis", wait: 1000 },
      { target: "#late", title: "C", body: "c" },
    ];
    registerTour("go-demo", steps);
    expect(runTour("go-demo")).toBe(true);
    await until(() => title() === "A");
    expect(document.body.classList.contains(ACTIVE_CLASS)).toBe(true);
    nextB()!.click();
    await until(() => title() === "B");
    expect(kbGo).toHaveBeenCalledTimes(1);
    expect(kbGo).toHaveBeenLastCalledWith("/graph?view=thesis");
    nextB()!.click();
    await until(() => title() === "C");
    expect(kbGo).toHaveBeenCalledTimes(1); // C inherits B's route: already there
    // Back onto B: still there. Back onto A: its route is Home, so the tour navigates there
    backB()!.click();
    await until(() => title() === "B");
    expect(kbGo).toHaveBeenCalledTimes(1);
    document.getElementById("home")?.remove(); // Home is not rendered while on the graph
    backB()!.click();
    await until(() => title() === "A");
    expect(kbGo).toHaveBeenCalledTimes(2);
    expect(kbGo).toHaveBeenLastCalledWith("/");
    nextB()!.click();
    await until(() => title() === "B");
    nextB()!.click();
    await until(() => title() === "C");
    nextB()!.click();
    expect(dock()).toBeNull();
    expect(document.body.classList.contains(ACTIVE_CLASS)).toBe(false);
    expect(seenTour("go-demo")).toBe(true);
  });

  it("ignores tour keys typed into a field", async () => {
    document.body.innerHTML = '<div id="a">a</div><input id="in" />';
    startTour([{ target: "#a", title: "A", body: "" }, { target: "#a", title: "B", body: "" }]);
    await until(() => title() === "A");
    const input = document.getElementById("in")!;
    input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await tick(50);
    expect(title()).toBe("A");
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await until(() => title() === "B");
    expect(title()).toBe("B");
  });

  it("a replaced run fires no side effects and is not marked seen", async () => {
    document.body.innerHTML = '<div id="a">a</div>';
    const before = vi.fn();
    registerTour("slow", [{ target: "#a", title: "S1", body: "" }, { target: "#a", title: "S2", body: "", before: async () => { await tick(200); before(); } }]);
    registerTour("fast", [{ target: "#a", title: "F1", body: "" }]);
    runTour("slow");
    await until(() => title() === "S1");
    nextB()!.click(); // S2's `before` is now pending
    runTour("fast");
    await until(() => title() === "F1");
    await tick(300);
    expect(before).toHaveBeenCalledTimes(1); // the awaited call returns, but nothing after it runs
    expect(title()).toBe("F1");
    expect(seenTour("slow")).toBe(false);
    skipB()!.click();
    expect(seenTour("fast")).toBe(true);
  });
});

describe("tour registry", () => {
  it("remembers a skipped tour and lists summaries", () => {
    registerTour("summ", [{ target: "body", title: "t", body: "b" }], "One line");
    expect(listTours().find((t) => t.name === "summ")).toEqual({ name: "summ", summary: "One line", seen: false });
    runTour("summ");
    skipB()!.click();
    expect(seenTour("summ")).toBe(true);
    expect(listTours().find((t) => t.name === "summ")?.seen).toBe(true);
    expect(runTour("nope")).toBe(false);
  });

  it("auto-starts the build's Home tour once, and not when seen, away from Home, embedded or with ?tour=", async () => {
    vi.useFakeTimers();
    registerTour("auto", [{ target: "body", title: "auto", body: "b" }]);
    registerTour("other", [{ target: "body", title: "other", body: "b" }]);
    globalThis.KB_EMBEDDED = { home: { tour: "auto" } } as never;
    installTours();
    await vi.advanceTimersByTimeAsync(700);
    expect(title()).toBe("auto");
    skipB()!.click();
    expect(seenTour("auto")).toBe(true);

    installTours(); // seen
    await vi.advanceTimersByTimeAsync(2000);
    expect(dock()).toBeNull();

    localStorage.clear();
    window.history.replaceState(null, "", "/graph"); // away from Home
    installTours();
    await vi.advanceTimersByTimeAsync(2000);
    expect(dock()).toBeNull();

    window.history.replaceState(null, "", "/?embed=1"); // embedded
    installTours();
    await vi.advanceTimersByTimeAsync(2000);
    expect(dock()).toBeNull();

    window.history.replaceState(null, "", "/?tour=other"); // an explicit tour wins
    installTours();
    await vi.advanceTimersByTimeAsync(2000);
    expect(title()).toBe("other");
    skipB()!.click();
    expect(seenTour("auto")).toBe(false);

    markSeen("auto");
    expect(window.kbTour?.list()).toContain("auto");
  });
});
