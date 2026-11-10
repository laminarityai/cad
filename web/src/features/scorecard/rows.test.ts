import { describe, expect, it } from "vitest";
import type { RequirementResult } from "@/api/types";
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

describe("a result this page does not know", () => {
  it("draws a requirement of an unknown kind as one unknown row and keeps the others", () => {
    const strange = { kind: "deferred", requirement_id: "r9", statement: "fit the bracket" } as unknown as RequirementResult;
    const rows = rowsOf(snapshot("v1", [mass("pass"), strange], [massResult()])).requirements;
    expect(rows.map((one) => one.kind)).toEqual(["settled", "settled"]);
    expect(rows[1]).toMatchObject({ key: "req:r9", label: "fit the bracket", verdict: "unknown" });
  });

  it("counts a verdict it does not know as unknown", () => {
    const strange = { ...mass("pass"), verdict: "inconclusive" } as unknown as RequirementResult;
    const rows = rowsOf(snapshot("v1", [strange], [massResult()])).requirements;
    expect(tally(rows)).toMatchObject({ pass: 0, fail: 0, unknown: 1, pending: 0 });
  });
});
