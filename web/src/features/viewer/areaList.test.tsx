import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AreaList } from "./AreaList";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the list of areas", () => {
  it("keeps one row for each area when two share a name and a colour", () => {
    const warned = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const body = { name: "body", colour: "#a6abb0" };
    const { rerender } = render(<AreaList areas={[{ ...body, faces: [0] }, { ...body, faces: [1] }]} greyed={null} />);
    rerender(<AreaList areas={[{ ...body, faces: [1] }, { ...body, faces: [0] }, { name: "grip", colour: "#1a1a1a", faces: [2] }]} greyed={null} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(warned.mock.calls.flat().join(" ")).not.toMatch(/same key/);
  });
});
