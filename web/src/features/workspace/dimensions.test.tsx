import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import type { DoneCheck } from "@/api/snapshot";
import type { Tessellated } from "@/api/types";
import { FakeChat, FakeViewer, fakeApi, meshOf } from "@/test/fakes";
import { massResult, snapshot } from "@/test/fixtures";
import { Workspace } from "./Workspace";

const bb = { xmin: -30, xmax: 30, ymin: 0, ymax: 40, zmin: 0, zmax: 70 };

/** The check's numbers differ from the mesh box's on purpose, so a label can only come from the check. */
const sized = (verdict: "pass" | "fail" | "unknown"): DoneCheck => ({
  ...massResult(),
  check_id: "extents",
  verdict,
  measured: [
    { name: "extent:x", value: { magnitude: 61, unit: "mm" } },
    { name: "extent:y", value: { magnitude: 41, unit: "mm" } },
    { name: "extent:z", value: { magnitude: 71, unit: "mm" } },
  ],
});

async function open(results: DoneCheck[]) {
  const viewer = new FakeViewer();
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] }),
    ),
    mesh: vi.fn((url: string) => Promise.resolve({ ...meshOf(url), shapes: { name: url, parts: [], bb } as unknown as Tessellated["shapes"] })),
    scorecard: vi.fn(() => Promise.resolve(snapshot("v1", [], results))),
  });
  render(
    <ServicesProvider services={{ api, viewer, chat: new FakeChat() }}>
      <MemoryRouter initialEntries={["/projects/p1"]}>
        <Routes>
          <Route path="projects/:projectId" element={<Workspace />} />
        </Routes>
      </MemoryRouter>
    </ServicesProvider>,
  );
  await waitFor(() => {
    expect(viewer.selected.length).toBeGreaterThan(0);
  });
  return viewer;
}

describe("the size check's dimensions", () => {
  it("draw the check's three numbers when Dimensions is on, and the toggle starts off", async () => {
    await open([sized("pass")]);
    const toggle = await screen.findByRole("button", { name: "Dimensions" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(document.querySelector("[data-dimensions]")).toBeNull();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    const overlay = document.querySelector("[data-dimensions]");
    if (!(overlay instanceof HTMLElement)) throw new Error("the overlay is missing");
    expect(overlay).toHaveTextContent("Size check");
    expect(["x", "y", "z"].map((axis) => overlay.querySelector(`[data-dimension="${axis}"]`)?.textContent)).toEqual(["61 mm", "41 mm", "71 mm"]);
    expect(overlay).not.toHaveTextContent("60 mm");
    await userEvent.click(toggle);
    expect(document.querySelector("[data-dimensions]")).toBeNull();
  });

  it.each([
    ["failed", [sized("fail")], "61 × 41 × 71 mm"],
    ["unknown", [sized("unknown")], "61 × 41 × 71 mm"],
    ["missing", [massResult()], "1 more passed"],
  ])("show no toggle and no lines when the size check is %s", async (_state, results, seen) => {
    await open(results);
    await screen.findAllByText(seen);
    expect(screen.queryByRole("button", { name: "Dimensions" })).toBeNull();
    expect(document.querySelector("[data-dimensions]")).toBeNull();
  });
});
