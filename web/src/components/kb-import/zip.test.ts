import { crc32, zipStore } from "./zip";

const bytes = (s: string) => new TextEncoder().encode(s);

describe("zipStore", () => {
  it("crc32 matches the standard check value", () => {
    expect(crc32(bytes("123456789"))).toBe(0xcbf43926);
  });

  it("writes local headers, a central directory and an end record", async () => {
    const blob = zipStore([{ path: "notes/a.md", data: bytes("# A") }, { path: "notes/é.md", data: bytes("x") }]);
    const buf = await new Promise<ArrayBuffer>((res) => { const r = new FileReader(); r.onload = () => res(r.result as ArrayBuffer); r.readAsArrayBuffer(blob); });
    const v = new DataView(buf);
    expect(v.getUint32(0, true)).toBe(0x04034b50);
    const end = buf.byteLength - 22;
    expect(v.getUint32(end, true)).toBe(0x06054b50);
    expect(v.getUint16(end + 10, true)).toBe(2);                       // entries
    const cd = v.getUint32(end + 16, true);
    expect(v.getUint32(cd, true)).toBe(0x02014b50);
    expect(v.getUint32(cd + 16, true)).toBe(crc32(bytes("# A")));
    expect(new TextDecoder().decode(new Uint8Array(buf, cd + 46, v.getUint16(cd + 28, true)))).toBe("notes/a.md");
  });
});
