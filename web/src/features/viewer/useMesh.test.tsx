import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import type { VariantView } from "@/api/types";
import { FakeChat, FakeViewer, fakeApi, meshOf } from "@/test/fakes";
import { useMesh } from "./useMesh";

const pendingView = (variantId: string): VariantView => ({
  variant_id: variantId,
  brep_sha256: "b".repeat(64),
  mesh: "pending",
  mesh_url: null,
});

function mount(api: ReturnType<typeof fakeApi>) {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ServicesProvider services={{ api, viewer: new FakeViewer(), chat: new FakeChat() }}>
      {children}
    </ServicesProvider>
  );
  return renderHook(({ variantId }: { variantId: string }) => useMesh(variantId), { wrapper, initialProps: { variantId: "v1" } });
}

describe("useMesh", () => {
  it("fetches a stored mesh from its immutable url and never starts a tessellation", async () => {
    const mesh = vi.fn((url: string) => Promise.resolve(meshOf(url)));
    const geometry = vi.fn();
    const { result } = mount(fakeApi(["v1"], { mesh, geometry }));
    await waitFor(() => {
      expect(result.current.status).toBe("ready");
    });
    expect(mesh).toHaveBeenCalledWith("/v1/geometry/0123456789ab/v1.json");
    expect(geometry).not.toHaveBeenCalled();
  });

  it("asks the geometry route to start the tessellation and asks again until it is done", async () => {
    const geometry = vi
      .fn()
      .mockResolvedValueOnce({ kind: "pending", brep_sha256: "b".repeat(64) })
      .mockResolvedValue(meshOf("v1"));
    const api = fakeApi(["v1"], { view: () => Promise.resolve(pendingView("v1")), geometry });
    const { result } = mount(api);
    expect(result.current.status).toBe("loading");
    await waitFor(
      () => {
        expect(result.current.status).toBe("ready");
      },
      { timeout: 3000 },
    );
    expect(geometry).toHaveBeenCalledTimes(2);
  });

  it("keeps the drawn mesh on screen while the next variant's mesh is made", async () => {
    const view = (variantId: string) => Promise.resolve(variantId === "v1" ? { ...pendingView("v1"), mesh: "tessellated" as const, mesh_url: "/v1/geometry/0123456789ab/v1.json" } : pendingView(variantId));
    const geometry = vi.fn(() => Promise.resolve({ kind: "pending" as const, brep_sha256: "b".repeat(64) }));
    const { result, rerender } = mount(fakeApi(["v1"], { view, geometry }));
    await waitFor(() => {
      expect(result.current.status).toBe("ready");
    });
    const drawn = result.current.status === "ready" ? result.current.shapes : null;
    rerender({ variantId: "v2" });
    await waitFor(() => {
      expect(geometry).toHaveBeenCalledWith("v2");
    });
    expect(result.current).toEqual({ status: "loading", lastDrawn: drawn });
  });

  it("says why a mesh failed", async () => {
    const geometry = vi.fn().mockResolvedValue({ kind: "failed", brep_sha256: "b", version: "v", reason: "not a solid" });
    const { result } = mount(fakeApi(["v1"], { view: () => Promise.resolve(pendingView("v1")), geometry }));
    await waitFor(() => {
      expect(result.current).toEqual({ status: "failed", reason: "not a solid" });
    });
  });
});
