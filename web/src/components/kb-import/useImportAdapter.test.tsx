import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { DataSourceProvider, type DataSource } from "@/api";
import { mockDataSource } from "@/test/datasource";
import { useImportAdapter } from "./useImportAdapter";

const env = vi.hoisted(() => ({ profile: null as "public" | "private" | null }));
vi.mock("@/share/env", () => ({
  get SHARE_PROFILE() {
    return env.profile;
  },
}));

const adapterFor = (kind: DataSource["kind"], profile: "public" | "private" | null) => {
  env.profile = profile;
  const ds = { ...mockDataSource(), kind } as DataSource;
  const wrapper = ({ children }: { children: ReactNode }) => <DataSourceProvider source={ds}>{children}</DataSourceProvider>;
  return renderHook(() => useImportAdapter(), { wrapper }).result.current;
};

describe("useImportAdapter by build", () => {
  it("the local app has an adapter", () => expect(adapterFor("http", null)).not.toBeNull());
  it("the private share build has one (the site inbox)", () => expect(adapterFor("embedded", "private")).not.toBeNull());
  it("a public snapshot has none, so it never shows the entry point", () => expect(adapterFor("embedded", "public")).toBeNull());
});
