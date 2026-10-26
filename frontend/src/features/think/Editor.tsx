/** React wrapper around a CodeMirror 6 view. Uncontrolled: the view owns the text between notes. */
import { useEffect, useRef } from "react";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, placeholder } from "@codemirror/view";
import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { thinkEditorExtensions } from "./livePreview";

export interface EditorProps {
  /** Note identity: a new key resets the buffer and the undo history. */
  noteKey: string;
  initialText: string;
  onChange: (text: string) => void;
  onSave: () => void;
  slugs: () => readonly string[];
}

export function Editor({ noteKey, initialText, onChange, onSave, slugs }: EditorProps) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const cb = useRef({ onChange, onSave, slugs });
  cb.current = { onChange, onSave, slugs };

  useEffect(() => {
    if (!host.current) return;
    const state = EditorState.create({
      doc: initialText,
      extensions: [
        history(),
        keymap.of([
          { key: "Mod-s", preventDefault: true, run: () => (cb.current.onSave(), true) },
          ...defaultKeymap,
          ...historyKeymap,
        ]),
        placeholder("Think here…"),
        thinkEditorExtensions(() => cb.current.slugs()),
        EditorView.updateListener.of((u) => {
          if (u.docChanged) cb.current.onChange(u.state.doc.toString());
        }),
      ],
    });
    const v = new EditorView({ state, parent: host.current });
    view.current = v;
    v.focus();
    return () => {
      view.current = null;
      v.destroy();
    };
    // a new note (noteKey) rebuilds the view with its own text + fresh undo history
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [noteKey]);

  return <div ref={host} className="min-h-[60vh] [&_.cm-editor]:min-h-[60vh]" data-testid="think-editor" />;
}
