import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";
import { DataSourceProvider, type DataSource } from "@/api";
import type { MarkDetail } from "@/api/types";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { DoubtMark } from "./DoubtMark";

const REF = "0123456789ab/p0188/3";
const mark = (over: Partial<MarkDetail> = {}): MarkDetail => ({
  id: 3, level: "!!", reason: "the two readers disagree", text: "$r = n - 1$", was: "$r = n$", other: "$r = n + 1$",
  page: "p0188", sha: "0123456789ab" + "0".repeat(28), crop_url: "/api/marks/0123456789ab/p0188/3/crop", resolution: null,
  read_only: false, ...over,
});

function show(over: Partial<DataSource>, props: { readOnly?: boolean } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DataSourceProvider source={mockDataSource(over)}>
        <DoubtMark ref_={REF} level="!!" slug="rank" {...props} />
      </DataSourceProvider>
    </QueryClientProvider>,
  );
}

describe("DoubtMark", () => {
  it("loads the mark only when opened, then Correct as is resolves it", async () => {
    await withFlag("parsed-pdf", true, async () => {
      const getMark = vi.fn(async () => mark());
      const resolveMark = vi.fn(async () => ({ ok: true, slug: "rank", commit: "abc", version: "kb-1.0.1" }));
      show({ getMark, resolveMark });
      expect(getMark).not.toHaveBeenCalled();
      expect(document.querySelector("img")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: /open the original/i }));
      expect(await screen.findByAltText(/original page/i)).toHaveAttribute("src", mark().crop_url);
      expect(screen.getByText("the two readers disagree")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Correct as is" }));
      await waitFor(() => expect(resolveMark).toHaveBeenCalledWith(REF, "rank"));
    });
  });

  it("Fix me proposes a formula, shows it rendered, and Approve applies it", async () => {
    await withFlag("parsed-pdf", true, async () => {
      const fixMark = vi.fn(async () => ({ replacement: "$r = n + 1$", current: "$r = n - 1$", backend: "subscription" }));
      const applyMark = vi.fn(async () => ({ ok: true, slug: "rank", commit: "abc", version: null }));
      show({ getMark: async () => mark(), fixMark, applyMark });
      fireEvent.click(screen.getByRole("button", { name: /open the original/i }));
      fireEvent.click(await screen.findByRole("button", { name: "Fix me" }));
      fireEvent.change(screen.getByRole("textbox"), { target: { value: "it is plus one" } });
      fireEvent.click(screen.getByRole("button", { name: "Propose a fix" }));
      await waitFor(() => expect(fixMark).toHaveBeenCalledWith(REF, { slug: "rank", instruction: "it is plus one", backend: "subscription" }));
      const proposal = await screen.findByTestId("doubt-proposal");
      expect(proposal.querySelector(".katex")).not.toBeNull();
      expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Approve" }));
      await waitFor(() => expect(applyMark).toHaveBeenCalledWith(REF, "rank", "$r = n + 1$"));
    });
  });

  it("read-only and no crop: shows the reason, hides the actions", async () => {
    await withFlag("parsed-pdf", false, async () => {
      show({ getMark: async () => mark({ crop_url: null, read_only: true }) });
      fireEvent.click(screen.getByRole("button", { name: /open the original/i }));
      expect(await screen.findByText("the two readers disagree")).toBeInTheDocument();
      expect(screen.getByText(/no image of the original/i)).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Correct as is" })).toBeNull();
      expect(screen.queryByRole("button", { name: "Fix me" })).toBeNull();
    });
  });
});
