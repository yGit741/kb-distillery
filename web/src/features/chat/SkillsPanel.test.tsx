import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DataSourceProvider, type ChatSkillList, type DataSource } from "@/api";
import { withFlag } from "@/flags/testing";
import { mockDataSource } from "@/test/datasource";
import { SkillsPanel } from "./SkillsPanel";
import { skillSelection } from "./skillsSelection";

const SID = "20261104101500-abc123";
const list = (on: Record<string, boolean>): ChatSkillList => ({
  session: SID,
  skills: [
    { name: "deep-research", description: "Answer a broad question with a cited report.", enabled: on["deep-research"] ?? true },
    { name: "query-knowledge", description: "Look something up in the wiki.", enabled: on["query-knowledge"] ?? true },
  ],
});

function setup(over: Partial<DataSource> = {}, kind: "http" | "embedded" = "http") {
  const ds = mockDataSource({ kind, ...over });
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DataSourceProvider source={ds}>
        <SkillsPanel sessionId={SID} />
      </DataSourceProvider>
    </QueryClientProvider>,
  );
}

/** Unmount before the flag is restored, so the restore does not re-render a live component. */
const inFlag = (on: boolean, fn: () => Promise<void> | void) =>
  on
    ? withFlag("agent-mode", true, async () => {
        try {
          await fn();
        } finally {
          cleanup();
        }
      })
    : withFlag("agent-mode", false, async () => {
        try {
          await fn();
        } finally {
          cleanup();
        }
      });

describe("SkillsPanel", () => {
  it("flag off: renders nothing and asks for nothing", async () => {
    await inFlag(false, () => {
      const listChatSkills = vi.fn(async () => list({}));
      const { container } = setup({ listChatSkills });
      expect(container).toBeEmptyDOMElement();
      expect(listChatSkills).not.toHaveBeenCalled();
    });
  });

  it("flag on in a share build: renders nothing", async () => {
    await inFlag(true, () => {
      const { container } = setup({}, "embedded");
      expect(container).toBeEmptyDOMElement();
    });
  });

  it("flag on: one row per skill with its description and a switch showing its state", async () => {
    await inFlag(true, async () => {
      setup({ listChatSkills: async () => list({ "query-knowledge": false }) });
      expect(await screen.findByRole("heading", { name: "Skills" })).toBeInTheDocument();
      const rows = await screen.findAllByRole("listitem");
      expect(rows).toHaveLength(2);
      expect(within(rows[0] as HTMLElement).getByText("Answer a broad question with a cited report.")).toBeInTheDocument();
      expect(screen.getByRole("switch", { name: "deep-research" })).toHaveAttribute("aria-checked", "true");
      expect(screen.getByRole("switch", { name: "query-knowledge" })).toHaveAttribute("aria-checked", "false");
    });
  });

  it("toggling calls PUT with the names left on, and the row follows", async () => {
    await inFlag(true, async () => {
      const putChatSkills = vi.fn(async (_id: string, body: { enabled: string[] }) => list({ "deep-research": body.enabled.includes("deep-research"), "query-knowledge": body.enabled.includes("query-knowledge") }));
      setup({ listChatSkills: async () => list({}), putChatSkills });
      const user = userEvent.setup();
      await user.click(await screen.findByRole("switch", { name: "deep-research" }));
      await waitFor(() => expect(putChatSkills).toHaveBeenCalledWith(SID, { enabled: ["query-knowledge"] }));
      await waitFor(() => expect(screen.getByRole("switch", { name: "deep-research" })).toHaveAttribute("aria-checked", "false"));
      expect(skillSelection(`kb-chat:${SID}`)).toEqual(["query-knowledge"]);
      await user.click(screen.getByRole("switch", { name: "deep-research" }));
      await waitFor(() => expect(putChatSkills).toHaveBeenLastCalledWith(SID, { enabled: ["deep-research", "query-knowledge"] }));
    });
  });

  it("a failed save puts the switch back and says so", async () => {
    await inFlag(true, async () => {
      setup({ listChatSkills: async () => list({}), putChatSkills: async () => { throw new Error("read-only server"); } });
      const user = userEvent.setup();
      await user.click(await screen.findByRole("switch", { name: "deep-research" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("read-only server");
      expect(screen.getByRole("switch", { name: "deep-research" })).toHaveAttribute("aria-checked", "true");
    });
  });

  it("empty whitelist: says so and names the kb.toml key", async () => {
    await inFlag(true, async () => {
      setup({ listChatSkills: async () => ({ skills: [], session: SID }) });
      expect(await screen.findByText(/No skills whitelisted for this knowledge base/)).toBeInTheDocument();
      expect(screen.getByText("[agent]")).toBeInTheDocument();
      expect(screen.getByText("kb.toml")).toBeInTheDocument();
      expect(screen.queryByRole("switch")).not.toBeInTheDocument();
    });
  });

  it("a load error shows a retry", async () => {
    await inFlag(true, async () => {
      setup({ listChatSkills: async () => { throw new Error("boom"); } });
      expect(await screen.findByRole("alert")).toHaveTextContent("boom");
      expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    });
  });
});
