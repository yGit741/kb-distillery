import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import type { DataSource } from "@/api";
import {
  CHAT_KEY,
  MIGRATED_KEY,
  MIRROR_DELAY_MS,
  chatIdOf,
  createMirror,
  createdOf,
  fromDoc,
  migrateBrowserChat,
  serverSessionsOn,
  sessionIdOf,
  toDoc,
} from "./serverStorage";
import { writeJson } from "./storage";
import type { Chat } from "./thread";

const chat = (id = "kb-chat:20261103101500-abc123", n = 2): Chat => ({
  id,
  session: "agent-1",
  messages: Array.from({ length: n }, (_, i) => ({ role: i % 2 ? "assistant" : "user", content: `m${i}` }) as Chat["messages"][number]),
});

const doc = (id: string): Awaited<ReturnType<DataSource["putSession"]>> =>
  ({ id, title: "t", created: "", updated: "", messages: [], usage: { cost_usd: 0, turns: 0 } }) as never;

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe("ids and documents", () => {
  it("maps a chat id to a plain server slug and back", () => {
    expect(sessionIdOf("kb-chat:20261103101500-abc123")).toBe("20261103101500-abc123");
    expect(chatIdOf("20261103101500-abc123")).toBe("kb-chat:20261103101500-abc123");
    expect(createdOf("kb-chat:20261103101500-abc123")).toBe("2026-11-03T10:15:00Z");
    expect(createdOf("something-else")).toBeUndefined();
  });

  it("toDoc sends the messages and times, not the title, session or empty fields", () => {
    const d = toDoc(chat(), { model: "m1", backend: "agent" });
    expect(d).toEqual({ messages: chat().messages, created: "2026-11-03T10:15:00Z", model: "m1", backend: "agent" });
    expect("title" in d).toBe(false);
    expect(fromDoc({ id: "x1", messages: [{ role: "user", content: "q" }] })).toEqual({ id: "kb-chat:x1", session: null, messages: [{ role: "user", content: "q" }] });
  });
});

describe("server sessions follow the backend, not a flag", () => {
  it("are on for the live backend, agent-mode on or off, and off in a share build", () => {
    const http = mockDataSource();
    withFlag("agent-mode", false, () => expect(serverSessionsOn(http)).toBe(true));
    withFlag("agent-mode", true, () => expect(serverSessionsOn(http)).toBe(true));
    expect(serverSessionsOn(mockDataSource({ kind: "embedded" }))).toBe(false);
  });
});

describe("createMirror", () => {
  it("sends one request per chat after the quiet period, with the newest state", async () => {
    const put = vi.fn(async (id: string) => doc(id));
    const synced = vi.fn();
    const m = createMirror({ putSession: put }, { onSynced: synced });
    m.schedule(chat(undefined, 2), { model: "a" });
    vi.advanceTimersByTime(MIRROR_DELAY_MS - 1);
    m.schedule(chat(undefined, 4), { model: "b" });
    vi.advanceTimersByTime(MIRROR_DELAY_MS - 1);
    expect(put).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2);
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.calls[0]![0]).toBe("20261103101500-abc123");
    expect((put.mock.calls[0] as unknown as [string, { messages: unknown[]; model: string }])[1]).toMatchObject({ model: "b", messages: chat(undefined, 4).messages });
    expect(synced).toHaveBeenCalledWith("20261103101500-abc123");
  });

  it("keeps requests in order and survives a failure", async () => {
    const order: string[] = [];
    let fail = true;
    const put = vi.fn(async (id: string, body: { messages: unknown[] }) => {
      if (fail) {
        fail = false;
        throw new Error("down");
      }
      order.push(`${id}:${body.messages.length}`);
      return doc(id);
    });
    const m = createMirror({ putSession: put });
    m.schedule(chat("kb-chat:20261103101500-aaaaaa", 2));
    m.schedule(chat("kb-chat:20261103101500-bbbbbb", 4));
    await m.flush();
    expect(put).toHaveBeenCalledTimes(2);
    expect(order).toEqual(["20261103101500-bbbbbb:4"]);
    m.schedule(chat("kb-chat:20261103101500-aaaaaa", 2));
    await m.flush();
    expect(order).toEqual(["20261103101500-bbbbbb:4", "20261103101500-aaaaaa:2"]);
  });

  it("ignores an empty chat, flushes on demand and cancels a deleted chat", async () => {
    const put = vi.fn(async (id: string) => doc(id));
    const m = createMirror({ putSession: put });
    m.schedule(chat(undefined, 0));
    await m.flush();
    expect(put).not.toHaveBeenCalled();
    m.schedule(chat());
    await m.flush();
    expect(put).toHaveBeenCalledTimes(1);
    m.schedule(chat());
    m.cancel(chat().id);
    await vi.advanceTimersByTimeAsync(MIRROR_DELAY_MS * 2);
    expect(put).toHaveBeenCalledTimes(1);
  });
});

describe("migrateBrowserChat", () => {
  it("copies the browser-held chat once and marks it, only after the server accepted it", async () => {
    writeJson("session", CHAT_KEY, chat());
    const put = vi.fn().mockRejectedValueOnce(new Error("down")).mockImplementation(async (id: string) => doc(id));
    expect(await migrateBrowserChat({ putSession: put })).toBe(false);
    expect(localStorage.getItem(MIGRATED_KEY)).toBeNull();
    expect(await migrateBrowserChat({ putSession: put })).toBe(true);
    expect(localStorage.getItem(MIGRATED_KEY)).toBe("true");
    expect(put).toHaveBeenCalledTimes(2);
    expect(put.mock.calls[1]![0]).toBe("20261103101500-abc123");
    expect(await migrateBrowserChat({ putSession: put })).toBe(false);
    expect(put).toHaveBeenCalledTimes(2);
  });

  it("marks the migration done when there is nothing to copy", async () => {
    const put = vi.fn();
    expect(await migrateBrowserChat({ putSession: put })).toBe(false);
    expect(localStorage.getItem(MIGRATED_KEY)).toBe("true");
    writeJson("session", CHAT_KEY, chat());
    expect(await migrateBrowserChat({ putSession: put })).toBe(false);
    expect(put).not.toHaveBeenCalled();
  });

  it("survives storage that throws", async () => {
    const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const put = vi.fn();
    await expect(migrateBrowserChat({ putSession: put })).resolves.toBe(false);
    spy.mockRestore();
  });
});

describe("createMirror failures", () => {
  it("reports a failed save to onError", async () => {
    const onError = vi.fn();
    const m = createMirror({ putSession: async () => Promise.reject(new Error("read-only")) }, { onError });
    m.schedule(chat());
    await m.flush();
    expect(onError).toHaveBeenCalledWith("20261103101500-abc123", "read-only");
  });
});
