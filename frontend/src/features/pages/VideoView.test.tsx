import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { DataSourceProvider, type DataSource } from "@/api";
import type { VideoBundle } from "@/api/types";
import { createEmbeddedDataSource } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { VideoView, displayMath, isVideoRaw } from "./VideoView";

const RAW = "raw/videos/svm/video.md";
const bundle: VideoBundle = {
  id: "abcdefghijk", title: "SVM", url: "https://www.youtube.com/watch?v=abcdefghijk", raw: RAW, channel: "MIT",
  duration: 600, description: "Notes at https://ocw.mit.edu", links: ["https://ocw.mit.edu"],
  chapters: [{ title: "Intro", start: 0, end: 300 }, { title: "Lagrange", start: 300, end: 600 }],
  comments: [{ author: "@a", likes: 3, text: "At 4:10 why is b free?", stamps: ["4:10"] }],
  subs_kind: "manual", tier: "frames",
  sections: [
    { chapter: "Intro", start: 0, end: 300, text: "Widest street." },
    { chapter: "Lagrange", start: 300, end: 600, text: "Lagrange multipliers." },
  ],
  frames: [
    { t: 400, file: "frame-00400.jpg", path: "raw/videos/svm/frame-00400.jpg", kind: "board", ocr: ["L ="],
      read: { text: "$$L = w$$\nDiagram: the street" } },
  ],
  stats: {},
};

const wrap = (ds: DataSource, node: ReactNode) => (
  <QueryClientProvider client={new QueryClient()}>
    <DataSourceProvider source={ds}>{node}</DataSourceProvider>
  </QueryClientProvider>
);

describe("VideoView", () => {
  it("shows chapters, comments and each frame in its section", async () => {
    const ds = mockDataSource({ getVideo: async () => bundle, rawFileUrl: (p) => `/api/raw/${p}/file` });
    render(wrap(ds, <VideoView raw={RAW} />));
    expect(await screen.findByRole("heading", { name: "Video" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Chapters" })).toHaveTextContent("Lagrange");
    expect(screen.getByRole("link", { name: "4:10" })).toHaveAttribute("href", "https://www.youtube.com/watch?v=abcdefghijk&t=250s");
    const img = screen.getByRole("img", { name: "Frame at 0:06:40" });
    expect(img).toHaveAttribute("src", "/api/raw/raw/videos/svm/frame-00400.jpg/file");
    expect(screen.getByText(/Diagram: the street/)).toBeInTheDocument();
  });

  it("renders nothing on a share build", () => {
    const { container } = render(wrap(createEmbeddedDataSource(), <VideoView raw={RAW} />));
    expect(container).toBeEmptyDOMElement();
  });

  it("shows an error with retry when the bundle cannot be read", async () => {
    const ds = mockDataSource({ getVideo: async () => { throw new Error("not a video bundle"); } });
    render(wrap(ds, <VideoView raw={RAW} />));
    expect(await screen.findByRole("alert")).toHaveTextContent("not a video bundle");
  });
});

describe("helpers", () => {
  it("knows a bundle's raw item", () => {
    expect(isVideoRaw(RAW)).toBe(true);
    expect(isVideoRaw("raw/printed-docs/2021-x.pdf")).toBe(false);
  });
  it("puts one-line $$…$$ on its own display block", () => {
    expect(displayMath("$$a$$\ntext")).toBe("\n$$\na\n$$\n\ntext");
  });
});
