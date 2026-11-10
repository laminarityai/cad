import { describe, expect, it } from "vitest";
import { restore, type SnapshotOnTheWire } from "./snapshot";
import { feaPending, mass, massResult, snapshot } from "@/test/fixtures";

describe("restore", () => {
  it("puts back what the server leaves out of an event", () => {
    const full = snapshot("v1", [mass("pass")], [massResult(), feaPending()]);
    const { not_verified: _a, research_problem: _b, research: _c, ...rest } = full;
    const lean: SnapshotOnTheWire = {
      ...rest,
      results: full.results.map((one) => {
        const { reads: _d, instance: _e, ...bare } = one;
        return bare;
      }),
    };
    expect(restore(lean)).toEqual(full);
  });
});
