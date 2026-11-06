import { mockDataSource } from "@/test/datasource";
import { exportPages } from "./runExport";

const src = (s: string, notes: string) => `---\ntype: idea\n---\n\n# ${s}\n\ntext\n\n## My notes\n\n${notes}\n`;

describe("exportPages", () => {
  const write = vi.fn(async () => {});
  beforeEach(() => {
    write.mockClear();
    Object.defineProperty(navigator, "clipboard", { value: { writeText: write }, configurable: true });
  });
  const ds = mockDataSource({ getPageSource: vi.fn(async (s: string) => src(s, `note-of-${s}`)) } as never);

  it("copies the bundle and says so", async () => {
    const say = vi.fn();
    await exportPages(ds, ["a", "b", "a"], { kbName: "Demo", isShare: false, say });
    const text = (write.mock.calls[0] as unknown as [string])[0];
    expect(text).toContain("# OKF bundle · 2 pages · Demo");
    expect(text).toContain("note-of-a");
    expect(say).toHaveBeenCalledWith("Copied 2 pages as an OKF bundle.");
  });

  it("never includes notes on the share build", async () => {
    await exportPages(ds, ["a"], { kbName: "Demo", isShare: true, say: vi.fn() });
    expect((write.mock.calls[0] as unknown as [string])[0]).not.toContain("note-of-a");
  });

  it("names what the cap cut", async () => {
    const say = vi.fn();
    const slugs = Array.from({ length: 62 }, (_, i) => `p${String(i).padStart(2, "0")}`);
    await exportPages(ds, slugs, { kbName: "Demo", isShare: false, say });
    expect(say.mock.calls[0]![0]).toMatch(/^Copied 60 pages as an OKF bundle\. 2 pages not included: p/);
  });
});
