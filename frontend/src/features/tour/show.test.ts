import { richText, startTour } from "./engine";
import { decodeShow, encodeShow, installTours } from "./tours";

const title = () => document.querySelector(".gt-card h4")?.textContent;
const tick = (ms = 0) => new Promise((r) => setTimeout(r, ms));
const until = async (ok: () => boolean, ms = 3000) => {
  const t0 = Date.now();
  while (!ok() && Date.now() - t0 < ms) await tick(20);
};

afterEach(() => {
  document.querySelector<HTMLButtonElement>(".gt-dock .gt-skip")?.click();
  document.body.innerHTML = "";
  window.history.replaceState(null, "", "/");
});

describe("show-me", () => {
  it("round-trips a script through the link, unicode included, and rejects junk", () => {
    const script = { title: "Legend — new ①", steps: [{ target: "#a", title: "T", body: "**b**" }] };
    const code = encodeShow(script);
    expect(code).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(decodeShow(code)).toEqual(script);
    expect(decodeShow("not-json")).toBeNull();
    expect(decodeShow(encodeShow({ title: "x", steps: [] }))).toBeNull();
  });

  it("card text escapes HTML, keeps **bold** and numbers [n] references", () => {
    expect(richText('<img src=x> **new** see [2]')).toBe('&lt;img src=x&gt; <strong>new</strong> see <span class="gt-n">2</span>');
  });

  it("rings every mark in its colour with a numbered label, and performs `do` actions", async () => {
    let clicks = 0;
    document.body.innerHTML = '<button id="a">a</button><div id="b">b</div><input id="c" />';
    document.getElementById("a")!.onclick = () => clicks++;
    startTour([
      { title: "Acted", body: "x", target: "#a", wait: 100, do: [{ click: "#a" }, { type: "#c", text: "hi" }], marks: [{ target: "#b", kind: "new", label: "new box" }, { target: "#gone" }] },
    ]);
    await until(() => title() === "Acted");
    expect(clicks).toBe(1);
    expect((document.getElementById("c") as HTMLInputElement).value).toBe("hi");
    await tick(30);
    const rings = [...document.querySelectorAll(".gt-ring")];
    expect(rings.map((r) => r.className)).toEqual(["gt-ring gt-k-focus", "gt-ring gt-k-new"]);   // a missing mark is dropped
    expect(rings[1]!.querySelector(".gt-tag")?.textContent).toBe("1new box");
  });

  it("?show= plays the script after an intro card, without registering it", async () => {
    document.body.innerHTML = '<div id="a">a</div>';
    window.history.replaceState(null, "", `/graph?show=${encodeShow({ title: "Look", steps: [{ target: "#a", title: "Step", body: "b" }] })}`);
    installTours();
    await until(() => title() === "Look");
    expect(window.kbTour!.list()).not.toContain("Look");
    document.querySelector<HTMLButtonElement>(".gt-dock .gt-next")!.click();
    await until(() => title() === "Step");
    expect(title()).toBe("Step");
  });

  it("a link never acts on its own: autoplay waits for the first Next, and nothing clicks before it", async () => {
    let clicks = 0;
    document.body.innerHTML = '<button id="a">a</button>';
    document.getElementById("a")!.onclick = () => clicks++;
    const steps = [{ title: "One", body: "b", target: "#a", do: [{ click: "#a" }] }, { title: "Two", body: "b" }, { title: "Three", body: "b" }];
    window.history.replaceState(null, "", `/?show=${encodeShow({ title: "Intro", steps, autoplay: 50 })}`);
    installTours();
    await until(() => title() === "Intro");
    await tick(400);
    expect(title()).toBe("Intro");
    expect(clicks).toBe(0);
    document.querySelector<HTMLButtonElement>(".gt-dock .gt-next")!.click();
    await until(() => title() === "Three");
    expect(clicks).toBe(1);
  });
});
