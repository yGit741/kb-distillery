import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { TypeRow } from "../../legendModel";
import { TypesCard } from "./TypesCard";
import { resetCorners, useCorners } from "./cornersStore";
import { groupTypes, pluralize } from "./typeGroups";

const row = (id: string, label: string, layer: TypeRow["layer"], total: number, shown = true): TypeRow => ({ id, label, layer, total, visible: total, shown });
const collections = [row("course", "Course", "collection", 11), row("series", "Series", "collection", 2), row("book", "Book", "collection", 2)];
const sources = [
  row("paper", "Paper", "source", 229),
  row("article", "Article", "source", 1),
  row("blog", "Blog", "source", 3),
  row("part", "Part", "source", 4),
];

describe("groupTypes", () => {
  it("folds the three collection types into one entry with the summed count", () => {
    const g = groupTypes(collections);
    expect(g).toHaveLength(1);
    expect(g[0]).toMatchObject({ label: "Collections", total: 15 });
    expect(g[0]!.members.map((m) => m.id)).toEqual(["course", "series", "book"]);
  });

  it("groups sources by glyph and pluralises the shared name", () => {
    const g = groupTypes(sources);
    expect(g.map((x) => [x.label, x.total])).toEqual([
      ["Papers", 229],
      ["Articles / posts", 4],
      ["Book parts", 4],
    ]);
  });

  it("a lone concept type keeps its own label; a lone source reads as its plural", () => {
    expect(groupTypes([row("topic", "Topic", "concept", 5)])[0]!.label).toBe("Topic");
    expect(groupTypes([row("paper", "Paper", "source", 5)])[0]!.label).toBe("Papers");
    expect(groupTypes([row("conversation", "Conversation", "source", 2)])[0]!.label).toBe("Mail");
  });

  it("a group counts as shown only when every member is", () => {
    const g = groupTypes([row("course", "Course", "collection", 1), row("series", "Series", "collection", 1, false)]);
    expect(g[0]!.shown).toBe(false);
  });

  it("pluralises in one place", () => {
    expect(pluralize("Article / post")).toBe("Articles / posts");
    expect(pluralize("Mail")).toBe("Mail");
    expect(pluralize("AI chat")).toBe("AI chats");
  });
});

describe("TypesCard groups", () => {
  beforeEach(() => {
    resetCorners();
    useCorners.getState().toggle("types");
  });

  const mount = (rows: TypeRow[], onToggle = vi.fn()) => {
    render(<TypesCard concepts={[]} sources={rows} onToggle={onToggle} onSpot={() => {}} />);
    return onToggle;
  };

  it("shows one entry for the three collection types, with the summed count", () => {
    mount(collections);
    expect(screen.getAllByRole("button", { name: /, \d+$/ })).toHaveLength(1);
    const b = screen.getByRole("button", { name: "Collections, 15" });
    expect(b.title).toContain("Course 11, Series 2, Book 2");
  });

  it("pressing a group hides all its members, and shows them all when one is hidden", async () => {
    const onToggle = mount(collections);
    await userEvent.click(screen.getByRole("button", { name: "Collections, 15" }));
    expect(onToggle).toHaveBeenLastCalledWith(["course", "series", "book"], false);
  });

  it("pressing a partly hidden group shows every member", async () => {
    const onToggle = mount([collections[0]!, { ...collections[1]!, shown: false }, collections[2]!]);
    await userEvent.click(screen.getByRole("button", { name: "Collections, 15" }));
    expect(onToggle).toHaveBeenLastCalledWith(["course", "series", "book"], true);
  });
});
