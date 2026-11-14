import { createMemoryHistory, createRootRoute, createRoute, createRouter, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import { withFlag } from "@/flags/testing";
import { figureUrl, inlineTag, Markdown, MathText, plainTitle, type MarkdownProps } from "./Markdown";

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

  it("routes [Title](slug.md) page links to /pages/<slug>, dropping the heading, and marks a missing page", async () => {
    await renderMd("See [Tensor rank](tensor-rank.md), [why](tensor-rank.md#why-it-works), [gone](ghost.md), [web](https://example.org/a.md).", {
      resolveSlug: (s) => (s === "ghost" ? null : s),
    });
    const links = screen.getAllByRole("link");
    expect(links[0]).toHaveAttribute("href", "/pages/tensor-rank");
    expect(links[0]).toHaveTextContent("Tensor rank");
    expect(links[1]).toHaveAttribute("href", "/pages/tensor-rank");
    expect(screen.getByText("gone")).toHaveAttribute("data-missing", "true");
    expect(links[2]).toHaveAttribute("href", "https://example.org/a.md");
  });

  it("shows a page link in a table cell and an escaped bracket label as text", async () => {
    const { container } = await renderMd("| a | b |\n|---|---|\n| [Alpha \\[1\\]](alpha.md) | x |");
    const a = container.querySelector("td a")!;
    expect(a).toHaveAttribute("href", "/pages/alpha");
    expect(a.textContent).toBe("Alpha [1]");
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

describe("Markdown unsure-formula marks", () => {
  const src = "Rank $r = n - 1$ [!!](mark:0123456789ab/p0188/3) here.";
  const doubt = { render: (ref: string, level: "!" | "!!") => <button type="button" data-ref={ref}>{level}</button> };

  it("draws the doubt hook after the formula when parsed-pdf is on", async () => {
    await withFlag("parsed-pdf", true, async () => {
      const { container } = await renderMd(src, { doubt });
      expect(container.querySelector(".katex")).not.toBeNull();
      const b = container.querySelector("button[data-ref]");
      expect(b?.getAttribute("data-ref")).toBe("0123456789ab/p0188/3");
      expect(b?.textContent).toBe("!!");
    });
  });

  it("is plain small text with no button when parsed-pdf is off", async () => {
    await withFlag("parsed-pdf", false, async () => {
      const { container } = await renderMd(src, { doubt });
      expect(container.querySelector("button")).toBeNull();
      expect(container.querySelector("[data-doubt]")?.textContent).toBe("!!");
      expect(container.querySelector("a")).toBeNull();
    });
  });

  it("drops a mark link whose target is not a mark ref", async () => {
    await withFlag("parsed-pdf", true, async () => {
      const { container } = await renderMd("x [!](mark:../../etc/passwd)", { doubt });
      expect(container.querySelector("button")).toBeNull();
    });
  });
});

describe("Markdown doubt tag on display formulas", () => {
  it("moves a mark on the line after $$…$$ into the equation's tag", async () => {
    await withFlag("parsed-pdf", true, async () => {
      const { container } = await renderMd("$$\nx = 1\n$$\n[!](mark:0123456789ab/p0188/4)\n\nAfter.", {
        doubt: { render: (ref) => <button type="button" data-ref={ref}>!</button> },
      });
      const wrap = container.querySelector(".kb-doubt-display");
      expect(wrap?.querySelector(".katex-display")).not.toBeNull();
      expect(wrap?.querySelector(".kb-doubt-tag button[data-ref]")).not.toBeNull();
    });
  });
});

describe("figures of a transcribed PDF", () => {
  it("maps a figure ref to its API url and nothing else", () => {
    expect(figureUrl("figure:0123456789ab/p0073/1")).toBe("/api/figures/0123456789ab/p0073/1");
    expect(figureUrl("figure:../../etc/p0073/1")).toBeNull();
    expect(figureUrl("https://example.com/x.png")).toBeNull();
  });

  it("renders the figure from the API with its label as alt text", async () => {
    const { container } = await renderMd("![Figure 3.1](figure:0123456789ab/p0073/1)\n\n**Figure 3.1.** A tree");
    const img = container.querySelector("img.kb-figure");
    expect(img?.getAttribute("src")).toBe("/api/figures/0123456789ab/p0073/1");
    expect(img?.getAttribute("alt")).toBe("Figure 3.1");
  });

  it("numbers an inline formula's \\tag instead of failing it", async () => {
    expect(inlineTag("q(x)=x,\\tag{1.11}")).toBe("q(x)=x,\\qquad(1.11)");
    const { container } = await renderMd("the polynomial $$q(x)=x,\\tag{1.11}$$ over the reals");
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.querySelector(".katex-error")).toBeNull();
  });

  it("typesets maths in a title and keeps plain titles as text", () => {
    const { container } = render(<h1><MathText text={"Decomposition of $W_QW_K^\\top$"} /></h1>);
    expect(container.querySelector("h1 .katex")).not.toBeNull();
    expect(container.querySelector("h1 p")).toBeNull();
    expect(render(<h1><MathText text="Plain title" /></h1>).container.textContent).toBe("Plain title");
    expect(plainTitle("Operator $W_QW_K^\\top$")).toBe("Operator W_QW_K^top");
  });
});
