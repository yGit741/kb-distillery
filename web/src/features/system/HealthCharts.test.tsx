import { render, screen, within } from "@testing-library/react";
import { coherenceBars, HealthCharts, inDegreeBars, lintIssueBars, phaseBars } from "./HealthCharts";
import { HealthView } from "./HealthView";

const graphs = {
  in_degree: { "0": 1, "1": 2, "2+": 24 },
  lint_phases_ms: { sha1: 0.2, wiki: 16.6, links: 3.3 },
  coherence_by_kind: { internal: 0, external: 3, cosmetic: 1 },
  lint_by_category: { errors: { wiki: 2, raw: 0 }, warnings: { wiki: 0, raw: 5, inbox: 0 } },
};

describe("health charts (the four charts of the old Health page)", () => {
  it("shape each series like the old chart", () => {
    expect(inDegreeBars(graphs).map((b) => [b.label, b.value])).toEqual([["0 inbound", 1], ["1 inbound", 2], ["2+ inbound", 24]]);
    expect(phaseBars(graphs).map((b) => b.label)).toEqual(["SHA1", "Wiki", "Links"]);
    expect(coherenceBars(graphs).map((b) => b.value)).toEqual([0, 3, 1]);
    // only categories with an error or a warning, errors before warnings
    expect(lintIssueBars(graphs).map((b) => [b.label, b.value])).toEqual([
      ["wiki · errors", 2], ["wiki · warnings", 0], ["raw · errors", 0], ["raw · warnings", 5],
    ]);
  });

  it("render four titled charts, and an empty note when no lint issue is open", () => {
    render(<HealthCharts health={{ graphs: { ...graphs, lint_by_category: { errors: {}, warnings: {} } } }} />);
    for (const t of ["Inbound links", "Lint phases", "Coherence by kind", "Lint issues"]) expect(screen.getByText(t)).toBeInTheDocument();
    expect(screen.getByText("No lint issues.")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Inbound links" })).getAllByRole("listitem")).toHaveLength(3);
  });

  it("render nothing for a snapshot without graphs", () => {
    const { container } = render(<HealthCharts health={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("the Health view adds the charts, the compression note and the metric help below the same cards", () => {
    render(
      <HealthView
        health={{ generated_at: "2026-11-01T10:00:00Z", values: { errors: 0 }, statuses: {}, graphs, compression_pct: 324, wiki_pages: 25, raw_files: 9 }}
        onRetry={() => {}}
      />,
    );
    expect(screen.getByTestId("health-charts")).toBeInTheDocument();
    expect(screen.getByText(/Wiki is ~324% of estimated raw tokens \(25 pages · 9 raw files\)/)).toBeInTheDocument();
    expect(screen.getByText("Lint errors")).toHaveAttribute("title", expect.stringMatching(/must be zero before commit/));
  });
});
