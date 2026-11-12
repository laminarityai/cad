import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import type { Tessellated } from "@/api/types";
import { FakeChat, FakeViewer, fakeApi, meshOf } from "@/test/fakes";
import { Workspace } from "./Workspace";

const bb = { xmin: -30, xmax: 30, ymin: 0, ymax: 40, zmin: 0, zmax: 70 };

async function open() {
  const viewer = new FakeViewer();
  const api = fakeApi(["v1"], {
    project: vi.fn(() =>
      Promise.resolve({ project_id: "p1", briefs: [{ brief_id: "b1", created_at: "2026-11-10T00:00:00Z", proposals: 1, confirmed_proposal: 1 }], context_parts: [], documents: [] }),
    ),
    mesh: vi.fn((url: string) => Promise.resolve({ ...meshOf(url), shapes: { name: url, parts: [], bb } as unknown as Tessellated["shapes"] })),
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

describe("the section", () => {
  it("starts off, and the toggle cuts the part across x in the middle and puts it back", async () => {
    const viewer = await open();
    const toggle = await screen.findByRole("button", { name: "Section" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("group", { name: "Section" })).toBeNull();
    expect(viewer.cut).toBeNull();
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("group", { name: "Section" })).toBeInTheDocument();
    await waitFor(() => {
      expect(viewer.cut).toEqual({ axis: "x", at: 0 });
    });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    expect(screen.queryByRole("group", { name: "Section" })).toBeNull();
    await waitFor(() => {
      expect(viewer.cut).toBeNull();
    });
  });

  it("moves the plane along the axis with the keyboard, in steps of the part's size", async () => {
    const viewer = await open();
    await userEvent.click(await screen.findByRole("button", { name: "Section" }));
    const slider = await screen.findByRole("slider", { name: "Position along x" });
    expect(slider).toHaveAttribute("min", "-30");
    expect(slider).toHaveAttribute("max", "30");
    slider.focus();
    await userEvent.keyboard("{ArrowRight}{ArrowRight}");
    await waitFor(() => {
      expect(viewer.cut).toEqual({ axis: "x", at: 1 });
    });
    expect(screen.getByText("Plane at x = 1.0 mm")).toBeInTheDocument();
    await userEvent.keyboard("{PageUp}");
    await waitFor(() => {
      expect(viewer.cut).toEqual({ axis: "x", at: 6 });
    });
    await userEvent.keyboard("{End}");
    await waitFor(() => {
      expect(viewer.cut).toEqual({ axis: "x", at: 30 });
    });
    await userEvent.keyboard("{Home}");
    await waitFor(() => {
      expect(viewer.cut).toEqual({ axis: "x", at: -30 });
    });
  });

  it("cuts across the axis the person picks, from the middle of the part along it", async () => {
    const viewer = await open();
    await userEvent.click(await screen.findByRole("button", { name: "Section" }));
    const group = await screen.findByRole("group", { name: "Cut across" });
    expect(group.querySelector("[data-axis=x]")).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(group.querySelector("[data-axis=z]") ?? group);
    await waitFor(() => {
      expect(viewer.cut).toEqual({ axis: "z", at: 35 });
    });
    expect(group.querySelector("[data-axis=z]")).toHaveAttribute("aria-pressed", "true");
    expect(group.querySelector("[data-axis=x]")).toHaveAttribute("aria-pressed", "false");
    const slider = screen.getByRole("slider", { name: "Position along z" });
    expect(slider).toHaveAttribute("min", "0");
    expect(slider).toHaveAttribute("max", "70");
    await userEvent.click(group.querySelector("[data-axis=z]") ?? group);
    expect(viewer.cut?.axis).toBe("z");
  });

  it("is said to be a position of the plane, never a size of the part", async () => {
    await open();
    await userEvent.click(await screen.findByRole("button", { name: "Section" }));
    const panel = await screen.findByRole("group", { name: "Section" });
    expect(panel).toHaveTextContent("Plane at x = 0.0 mm");
    expect(panel).not.toHaveTextContent(/thick|wall|size|depth/i);
  });
});
