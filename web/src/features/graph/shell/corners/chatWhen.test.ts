import { chatWhen } from "./api";

const now = new Date(2026, 10, 5, 12, 0);
const at = (y: number, m: number, d: number) => new Date(y, m, d, 9, 0).toISOString();

describe("chatWhen", () => {
  it("names the status while the chat is doing something", () => {
    expect(chatWhen({ status: "running", updated: at(2026, 9, 1) }, now)).toBe("running");
    expect(chatWhen({ status: "waiting" }, now)).toBe("waiting");
    expect(chatWhen({ status: "error" }, now)).toBe("failed");
  });
  it("else the day of the last turn, like the mockup", () => {
    expect(chatWhen({ status: "idle", updated: at(2026, 10, 5) }, now)).toBe("today");
    expect(chatWhen({ updated: at(2026, 10, 4) }, now)).toBe("yesterday");
    expect(chatWhen({ updated: at(2026, 9, 30) }, now)).toBe("Oct 30");
    expect(chatWhen({ updated: at(2025, 9, 30) }, now)).toBe("Oct 30, 2025");
    expect(chatWhen({ updated: "nonsense" }, now)).toBe("");
    expect(chatWhen({}, now)).toBe("");
  });
});
