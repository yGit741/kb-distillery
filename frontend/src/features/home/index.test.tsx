import { render } from "@testing-library/react";
import type { HomeHost } from "./HomeScreen";

const navigate = vi.fn();
let captured: HomeHost | undefined;
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate, useSearch: () => ({}) }));
vi.mock("./HomeScreen", () => ({ HomeScreen: ({ host }: { host: HomeHost }) => ((captured = host), null) }));

import Home from "./index";

describe("Home route", () => {
  it("picking a concept replaces the URL and keeps the scroll position", () => {
    render(<Home />);
    captured!.setConcept!("hub");
    expect(navigate).toHaveBeenCalledWith(expect.objectContaining({ to: "/", search: { concept: "hub" }, replace: true, resetScroll: false }));
  });
});
