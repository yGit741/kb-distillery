import { render, screen } from "@testing-library/react";
import { node } from "../fixtures";
import { ACTION_ITEMS, visibleItems } from "../menu";
import { Inspector } from "../Inspector";
import { useFavorites } from "./store";
import { withFlag } from "@/flags/testing";

vi.mock("@/share/env", () => ({ IS_SHARE: true, SHARE_PROFILE: "public" }));

const n = node("a-page", { title: "A page" });

describe("favorites on the share build", () => {
  it("has no toggle in the menu or the inspector, and a favorite only shows its mark", async () => {
    expect(visibleItems(n, ACTION_ITEMS).map((i) => i.id)).not.toContain("favorite");
    useFavorites.setState({ slugs: new Set(["a-page"]) });
    withFlag("graph-intent", true, () => {
      render(<Inspector nodes={[n]} byId={new Map([[n.id, n]])} neighbors={new Map()} colorBy="type" revealed={new Set()} pageHref={() => "#"} onClose={() => {}} onClear={() => {}} onFocus={() => {}} onRead={() => {}} onToggleSources={() => {}} />);
    });
    expect(screen.getByRole("img", { name: "Favorite" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /favorites/i })).toBeNull();
  });
});
