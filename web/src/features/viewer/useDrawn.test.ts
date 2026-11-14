import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Shapes } from "./engine";
import { useDrawn, withFit } from "./useDrawn";
import type { Where } from "./where";

const piece = (id: string) => ({
  id,
  name: id,
  color: "#a6abb0",
  alpha: 1,
  shape: { triangles: [0, 1, 2, 0, 1, 2], triangles_per_face: [1, 1], vertices: [], normals: [], edges: [], segments_per_edge: [], edge_types: [], obj_vertices: [], face_types: [0, 0] },
});
const shapesOf = (id: string, bb: Partial<Shapes["bb"]> = {}) =>
  ({ id: "/variant", name: "variant", parts: [piece(id)], bb: { xmin: 0, xmax: 1, ymin: 0, ymax: 1, zmin: 0, zmax: 1, ...bb } }) as unknown as Shapes;

const part = shapesOf("/variant/part");
const ghost = shapesOf("/variant/part", { xmax: 5 });

describe("withFit", () => {
  it("adds the context part as a faint ghost under /fit and widens the box to both", () => {
    const both = withFit(part, ghost);
    expect(both.parts.map((one) => one.id)).toEqual(["/variant/part", "/fit/variant/part"]);
    expect(both.parts[1]?.alpha).toBe(0.22);
    expect(both.bb.xmax).toBe(5);
  });
});

describe("useDrawn", () => {
  it("hands back the same shapes while the mesh, the ghost and the marked faces are unchanged", () => {
    const where = (): Where => ({ support: [0], load: [1] });
    const view = renderHook((props: { where: Where | null }) => useDrawn(part, ghost, props.where), { initialProps: { where: where() } });
    const first = view.result.current;
    view.rerender({ where: where() });
    expect(view.result.current).toBe(first);
  });

  it("makes new shapes when the marked faces, the ghost or the mesh change", () => {
    const view = renderHook((props: { part: Shapes; ghost: Shapes | null; where: Where | null }) => useDrawn(props.part, props.ghost, props.where), {
      initialProps: { part, ghost: null as Shapes | null, where: null as Where | null },
    });
    const bare = view.result.current;
    view.rerender({ part, ghost, where: null });
    const withGhost = view.result.current;
    expect(withGhost).not.toBe(bare);
    view.rerender({ part, ghost, where: { support: [0], load: [] } });
    const marked = view.result.current;
    expect(marked).not.toBe(withGhost);
    view.rerender({ part, ghost, where: { support: [0], load: [1] } });
    expect(view.result.current).not.toBe(marked);
    view.rerender({ part: shapesOf("/variant/part"), ghost, where: { support: [0], load: [1] } });
    expect(view.result.current).not.toBe(marked);
  });

  it("draws the areas in their colours, and only the stress faces on grey while those are marked", () => {
    const areas = [{ name: "grip", colour: "#1a1a1a", faces: [1] }];
    const view = renderHook((props: { where: Where | null }) => useDrawn(part, null, props.where, areas), { initialProps: { where: null as Where | null } });
    expect(view.result.current?.parts.map((one) => [one.id, one.color])).toEqual([
      ["/variant/part", "#a6abb0"],
      ["/variant/area/0", "#1a1a1a"],
    ]);
    view.rerender({ where: { support: [0], load: [] } });
    expect(view.result.current?.parts.map((one) => one.id)).toEqual(["/variant/part", "/variant/support"]);
  });

  it("draws nothing before there is a part", () => {
    expect(renderHook(() => useDrawn(null, ghost, null)).result.current).toBeNull();
  });
});
