import { EditorView } from "@codemirror/view";
import { createMemoryHistory } from "@tanstack/react-router";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { ApiError, type DataSource } from "@/api";
import { useUi } from "@/app/ui-store";
import { mockDataSource } from "@/test/datasource";

// CodeMirror measures real layout; jsdom has none, so give it harmless geometry.
const rect = { top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;
const noRects = function (this: unknown) {
  return Object.assign([] as DOMRect[], { item: () => null }) as unknown as DOMRectList;
};
beforeAll(() => {
  Range.prototype.getClientRects = noRects;
  Range.prototype.getBoundingClientRect = () => rect;
  Element.prototype.getClientRects = noRects;
  Element.prototype.scrollIntoView = () => undefined;
});

const notes = [
  { name: "thesis-decision.md", size: 20, mtime: Date.now() / 1000 - 60 },
  { name: "reading-notes.md", size: 10, mtime: Date.now() / 1000 - 86400 },
];
const note = { name: "thesis-decision.md", text: "# Thesis\n\nstill open\n", mtime: notes[0]!.mtime };

function setup(over: Partial<DataSource> = {}, url = "/app/think") {
  const ds = mockDataSource({
    listThink: async () => ({ notes, capture_note: "inbox.md" }),
    getThinkNote: async (name) => ({ ...note, name }),
    listPages: async () => ({ generated_at: "", pages: [], links: [], wanted: [], wanted_total: 0 }),
    getShareStatus: async () => ({ status: null, chip: null }),
    ...over,
  });
  const router = createAppRouter(createMemoryHistory({ initialEntries: [url] }));
  render(<App source={ds} router={router} />);
  return { ds, router };
}

describe("ThinkScreen", () => {
  beforeEach(() => useUi.setState({ captureOpen: false }));

  it("lists notes and opens the newest in the editor", async () => {
    setup();
    expect(await screen.findByText("thesis-decision")).toBeInTheDocument();
    expect(screen.getByText("reading-notes")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("think-editor").textContent).toContain("still open"));
    expect(screen.getByText("Yours alone — agents never write here.")).toBeInTheDocument();
  });

  it("opens the note named in the URL", async () => {
    const getThinkNote = vi.fn(async (name: string) => ({ ...note, name }));
    setup({ getThinkNote }, "/app/think?note=reading-notes.md");
    await waitFor(() => expect(getThinkNote).toHaveBeenCalledWith("reading-notes.md"));
  });

  it("empty think/ offers a first note", async () => {
    setup({ listThink: async () => ({ notes: [], capture_note: "inbox.md" }) });
    expect(await screen.findByText(/think\/ is empty/)).toBeInTheDocument();
  });

  it("list error shows retry", async () => {
    setup({ listThink: async () => Promise.reject(new ApiError("backend down", 404)) });
    expect(await screen.findByText("Could not read think/")).toBeInTheDocument();
  });

  it("typing autosaves with the optimistic lock", async () => {
    const saveThinkNote = vi.fn(async () => ({ name: note.name, mtime: note.mtime + 1, created: false }));
    setup({ saveThinkNote });
    await waitFor(() => expect(screen.getByTestId("think-editor").textContent).toContain("still open"));
    const view = EditorView.findFromDOM(screen.getByTestId("think-editor"))!;
    view.dispatch({ changes: { from: view.state.doc.length, insert: "more" } });
    fireEvent.keyDown(view.contentDOM, { key: "s", ctrlKey: true }); // Mod = Ctrl off-mac (jsdom)
    await waitFor(() => expect(saveThinkNote).toHaveBeenCalled());
    const [name, body] = saveThinkNote.mock.calls[0]! as unknown as [string, { text: string; base_mtime: number }];
    expect(name).toBe("thesis-decision.md");
    expect(body.text).toContain("more");
    expect(body.base_mtime).toBe(note.mtime);
    await screen.findByText("Saved");
  });
});

describe("ThinkScreen save races", () => {
  it("text typed while a save is in flight is not lost", async () => {
    let release!: (v: { name: string; mtime: number; created: boolean }) => void;
    const first = new Promise<{ name: string; mtime: number; created: boolean }>((r) => (release = r));
    const saveThinkNote = vi
      .fn()
      .mockImplementationOnce(() => first)
      .mockImplementation(async () => ({ name: note.name, mtime: note.mtime + 2, created: false }));
    setup({ saveThinkNote });
    await waitFor(() => expect(screen.getByTestId("think-editor").textContent).toContain("still open"));
    const view = EditorView.findFromDOM(screen.getByTestId("think-editor"))!;
    view.dispatch({ changes: { from: view.state.doc.length, insert: "T1" } });
    fireEvent.keyDown(view.contentDOM, { key: "s", ctrlKey: true }); // save T1, held in flight
    view.dispatch({ changes: { from: view.state.doc.length, insert: "T2" } }); // typed meanwhile
    release({ name: note.name, mtime: note.mtime + 1, created: false });
    await waitFor(() => expect(screen.getByText("Editing · saves itself")).toBeInTheDocument()); // still dirty, not "Saved"
    fireEvent.keyDown(view.contentDOM, { key: "s", ctrlKey: true }); // flush T2
    await waitFor(() => expect(saveThinkNote).toHaveBeenCalledTimes(2));
    const second = saveThinkNote.mock.calls[1]! as unknown as [string, { text: string; base_mtime: number }];
    expect(second[1].text).toContain("T1T2");
    expect(second[1].base_mtime).toBe(note.mtime + 1); // the first save's result, not a stale base
    await screen.findByText("Saved");
  });

  it("creating a note that already exists opens it instead of truncating it", async () => {
    const saveThinkNote = vi.fn();
    vi.spyOn(window, "prompt").mockReturnValue("thesis-decision");
    setup({ saveThinkNote });
    await screen.findByText("thesis-decision");
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "New note" }));
    await waitFor(() => expect(saveThinkNote).not.toHaveBeenCalled());
  });
});

describe("QuickCapture", () => {
  it("captures a thought from anywhere and confirms", async () => {
    const captureThink = vi.fn(async () => ({ name: "inbox.md", mtime: 1, created: false }));
    setup({ captureThink }, "/app/");
    useUi.getState().setCaptureOpen(true);
    const user = userEvent.setup();
    const area = await screen.findByPlaceholderText("A quick thought…");
    await user.type(area, "call the advisor");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(captureThink).toHaveBeenCalledWith("call the advisor"));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved to think/inbox.md");
  });
});
