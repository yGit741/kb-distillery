import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import { Markdown, type MarkdownProps } from "./Markdown";

async function renderMd(source: string, props: Partial<MarkdownProps> = {}) {
  const root = createRootRoute();
  const page = createRoute({
    getParentRoute: () => root,
    path: "/pages/$slug",
    component: () => null,
  });
  const index = createRoute({
    getParentRoute: () => root,
    path: "/",
    component: () => <Markdown {...props}>{source}</Markdown>,
  });
  const router = createRouter({
    routeTree: root.addChildren([index, page]),
    history: createMemoryHistory({ initialEntries: ["/"] }),
  });
  const out = render(<RouterProvider router={router} />);
  await waitFor(() => expect(out.container.querySelector(".kb-prose")).not.toBeNull());
  return { ...out, router };
}

describe("Markdown", () => {
  it("renders GFM: tables, task lists, strikethrough", async () => {
    const { container } = await renderMd("| a | b |\n|---|---|\n| 1 | 2 |\n\n- [x] done\n\n~~gone~~");
    expect(container.querySelector("table")).not.toBeNull();
    expect(container.querySelector('input[type="checkbox"]')).not.toBeNull();
    expect(container.querySelector("del")).not.toBeNull();
  });

  it("renders inline and display math with KaTeX", async () => {
    const { container } = await renderMd("Inline $x^2$ and\n\n$$\n\\sum_{i=1}^n i\n$$");
    expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(2);
    expect(container.querySelector(".katex-display")).not.toBeNull();
  });

  it("highlights fenced code", async () => {
    const { container } = await renderMd("```python\ndef f():\n    return 1\n```");
    expect(container.querySelector("code.hljs, code.language-python")).not.toBeNull();
    expect(container.querySelector(".hljs-keyword")).not.toBeNull();
  });

  it("turns [[slug]] and [[slug|label]] into links to /pages/<slug>", async () => {
    await renderMd("See [[paper-2023-toolformer]] and [[tensor-rank|rank]].");
    expect(screen.getByRole("link", { name: "paper-2023-toolformer" })).toHaveAttribute("href", "/pages/paper-2023-toolformer");
    expect(screen.getByRole("link", { name: "rank" })).toHaveAttribute("href", "/pages/tensor-rank");
  });

  it("uses resolveSlug to follow renames and to mark missing pages", async () => {
    await renderMd("[[old-name]] and [[ghost]]", {
      resolveSlug: (s) => (s === "old-name" ? "new-name" : null),
    });
    expect(screen.getByRole("link", { name: "old-name" })).toHaveAttribute("href", "/pages/new-name");
    expect(screen.queryByRole("link", { name: "ghost" })).toBeNull();
    expect(screen.getByText("ghost")).toHaveAttribute("data-missing", "true");
  });

  it("leaves [[x]] alone inside code", async () => {
    const { container } = await renderMd("`[[not-a-link]]`\n\n```\n[[also-not]]\n```");
    expect(container.querySelectorAll("a")).toHaveLength(0);
    expect(container.textContent).toContain("[[not-a-link]]");
  });

  it("does not render raw HTML or script", async () => {
    const { container } = await renderMd('<script>window.__x=1</script><img src=x onerror="window.__x=2"><b>bold</b>\n\ntext');
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("b")).toBeNull();
    expect((window as unknown as { __x?: number }).__x).toBeUndefined();
  });

  it("drops javascript: links and opens external links safely", async () => {
    const { container } = await renderMd("[bad](javascript:alert(1)) [ok](https://example.org)");
    const links = [...container.querySelectorAll("a")];
    expect(links.find((a) => a.textContent === "bad")?.getAttribute("href") ?? "").toBe("");
    const ok = links.find((a) => a.textContent === "ok")!;
    expect(ok).toHaveAttribute("href", "https://example.org");
    expect(ok).toHaveAttribute("rel", "noopener noreferrer");
  });
});
