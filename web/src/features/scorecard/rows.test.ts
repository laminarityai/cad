import { describe, expect, it } from "vitest";
import { deflection, feaPending, mass, massResult, snapshot } from "@/test/fixtures";
import { ghostsOf, pendingFrom, rowsOf, tally } from "./rows";

describe("rowsOf", () => {
  const card = snapshot("v1", [mass("pass"), deflection()], [massResult(41.2), feaPending()]);

  it("makes a waiting requirement a pending row that has no verdict field", () => {
    const [, waiting] = rowsOf(card).requirements;
    expect(waiting).toMatchObject({ kind: "pending", check: "fea" });
    expect(waiting).not.toHaveProperty("verdict");
  });

  it("shows the measured value beside the limit", () => {
    const [settled] = rowsOf(card).requirements;
    expect(settled).toMatchObject({ kind: "settled", verdict: "pass", measures: ["mass 41.2 g ≤ 50 g"] });
  });

  it("tallies pending apart from verdicts", () => {
    expect(tally(rowsOf(card).requirements)).toMatchObject({ pass: 1, pending: 1, fail: 0, unknown: 0 });
  });
});

describe("pendingFrom", () => {
  it("turns every settled row of the earlier revision pending and keeps its text as the ghost", () => {
    const before = snapshot("v1", [mass("fail")], [massResult(61)]);
    const rows = pendingFrom(rowsOf(before));
    expect(rows.requirements.every((one) => one.kind === "pending")).toBe(true);
    expect(rows.checks.every((one) => one.kind === "pending")).toBe(true);
    expect(ghostsOf(before)["req:r1"]).toBe("mass 61 g ≤ 50 g");
  });
});
