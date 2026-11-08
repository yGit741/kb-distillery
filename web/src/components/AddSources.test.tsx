import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ApiError, DataSourceProvider, type DataSource } from "@/api";
import { createHttpDataSource } from "@/api/http";
import { mockDataSource } from "@/test/datasource";
import { AddSources } from "./AddSources";

function show(over: Partial<DataSource>) {
  render(
    <DataSourceProvider source={mockDataSource(over)}>
      <QueryClientProvider client={new QueryClient()}>
        <AddSources />
      </QueryClientProvider>
    </DataSourceProvider>,
  );
}

const file = (name: string) => new File(["hello"], name, { type: "text/plain" });

describe("AddSources", () => {
  it("a picked file goes to the endpoint and all three statuses render", async () => {
    const addInboxFiles = vi.fn(async () => ({
      files: [
        { name: "a.txt", status: "added" },
        { name: "b.txt", status: "duplicate" },
        { name: "c.exe", status: "refused", reason: "unsupported type" },
      ],
    }));
    show({ addInboxFiles });
    const a = file("a.txt");
    await userEvent.upload(screen.getByTestId("add-sources-input"), [a, file("b.txt"), file("c.exe")]);
    expect(addInboxFiles).toHaveBeenCalledTimes(1);
    expect((addInboxFiles.mock.calls[0] as unknown as [File[]])[0]).toHaveLength(3);
    const list = await screen.findByRole("list", { name: "Add results" });
    expect(within(list).getByText("Added")).toBeInTheDocument();
    expect(within(list).getByText("Already here")).toBeInTheDocument();
    expect(within(list).getByText("Refused: unsupported type")).toBeInTheDocument();
  });

  it("a dropped file goes to the endpoint and the zone highlights while dragging", async () => {
    const addInboxFiles = vi.fn(async () => ({ files: [{ name: "d.txt", status: "added" }] }));
    show({ addInboxFiles });
    const zone = screen.getByRole("button", { name: /drop files here/i });
    fireEvent.dragOver(zone);
    expect(zone).toHaveAttribute("data-over", "true");
    fireEvent.drop(zone, { dataTransfer: { files: [file("d.txt")] } });
    await waitFor(() => expect(addInboxFiles).toHaveBeenCalledTimes(1));
    expect(zone).toHaveAttribute("data-over", "false");
    expect(await screen.findByText("Added")).toBeInTheDocument();
  });

  it("the folder form posts the path and shows the count", async () => {
    const linkInboxFolder = vi.fn(async () => ({ linked: true, files_catalogued: 3, skipped: 0 }));
    show({ linkInboxFolder });
    await userEvent.type(screen.getByPlaceholderText(/folder path/), "/Users/jdoe/papers");
    await userEvent.click(screen.getByRole("button", { name: "Link" }));
    expect(linkInboxFolder).toHaveBeenCalledWith("/Users/jdoe/papers");
    expect(await screen.findByText(/3 files catalogued/)).toBeInTheDocument();
  });

  it("an API error renders as one plain line", async () => {
    show({
      addInboxFiles: async () => { throw new ApiError("This knowledge base is read-only.", 405); },
      linkInboxFolder: async () => { throw new ApiError("No such folder.", 400); },
    });
    await userEvent.upload(screen.getByTestId("add-sources-input"), file("a.txt"));
    expect(await screen.findByText("This knowledge base is read-only.")).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText(/folder path/), "/nope");
    await userEvent.click(screen.getByRole("button", { name: "Link" }));
    expect(await screen.findByText("No such folder.")).toBeInTheDocument();
  });
});

describe("http data source: inbox", () => {
  it("posts multipart files and maps 413 to a plain line", async () => {
    const fetchImpl = vi.fn(async (_p: RequestInfo | URL, init?: RequestInit) =>
      init?.body instanceof FormData ? new Response(JSON.stringify({ detail: "File too large" }), { status: 413 }) : new Response("{}"),
    );
    const ds = createHttpDataSource(fetchImpl as unknown as typeof fetch, "http://x");
    await expect(ds.addInboxFiles([file("a.txt")])).rejects.toMatchObject({ message: "File too large", status: 413 });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/api/inbox/files");
  });

  it("posts the folder path as JSON", async () => {
    const fetchImpl = vi.fn(async () => new Response(JSON.stringify({ linked: true, files_catalogued: 2, skipped: 0 })));
    const ds = createHttpDataSource(fetchImpl as unknown as typeof fetch, "http://x");
    const r = await ds.linkInboxFolder("/p");
    expect(r.files_catalogued).toBe(2);
    const call = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(call[0]).toBe("/api/inbox/link-folder");
    expect(call[1].body).toBe(JSON.stringify({ path: "/p" }));
  });
});
