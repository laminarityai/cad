import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { FakeChat, FakeViewer, fakeApi } from "@/test/fakes";
import type { DoneCheck, Scorecard } from "@/api/snapshot";
import type { Checked, Specimen } from "@/api/types";
import { deflectionDone, feaMeasureOnly, feaPending, massResult, snapshot } from "@/test/fixtures";
import { restore } from "@/api/snapshot";
import { assumedOf, awaitingOf, linesOf, passedExtents, summaryOf, useCards, type CardKey } from "./cards";

const settle = () => act(() => vi.advanceTimersByTimeAsync(0));
const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

const wire = (variantId: string) => snapshot(variantId, [], [massResult()]);

function mount(scorecard: ReturnType<typeof fakeApi>["scorecard"], initial: CardKey[]) {
  const api = fakeApi([], { scorecard });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ServicesProvider services={{ api, viewer: new FakeViewer(), chat: new FakeChat() }}>{children}</ServicesProvider>
  );
  return renderHook(({ keys }: { keys: CardKey[] }) => useCards(keys), { wrapper, initialProps: { keys: initial } });
}

const key = (variantId: string, materialKey: string | null = "pla", briefId = "b1"): CardKey => ({ variantId, materialKey, briefId });

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useCards", () => {
  it("reads each card once on first load, with its brief and material, and again every 1.5 s", async () => {
    const scorecard = vi.fn((variantId: string) => Promise.resolve(wire(variantId)));
    const { result } = mount(scorecard, [key("v1"), key("v2", null, "b2"), key("v1")]);
    await settle();
    expect(scorecard.mock.calls).toEqual([
      ["v1", "b1", "pla"],
      ["v2", "b2", null],
    ]);
    expect(Object.keys(result.current)).toEqual(["v1", "v2"]);
    expect(result.current.v1?.snapshot?.variant_id).toBe("v1");
    await tick(1500);
    expect(scorecard).toHaveBeenCalledTimes(4);
  });

  it("has no card until the first answer, and an empty one when the first read fails", async () => {
    const scorecard = vi.fn().mockRejectedValueOnce(new Error("down")).mockImplementation((variantId: string) => Promise.resolve(wire(variantId)));
    const { result } = mount(scorecard, [key("v1")]);
    expect(result.current).toEqual({});
    await settle();
    expect(result.current.v1?.snapshot).toBeNull();
    await tick(1500);
    expect(result.current.v1?.snapshot?.variant_id).toBe("v1");
  });

  it("keeps a card's last snapshot when a later read fails", async () => {
    const scorecard = vi.fn().mockResolvedValueOnce(wire("v1")).mockRejectedValue(new Error("down"));
    const { result } = mount(scorecard, [key("v1")]);
    await settle();
    await tick(1500);
    expect(scorecard).toHaveBeenCalledTimes(2);
    expect(result.current.v1?.snapshot?.variant_id).toBe("v1");
  });

  it("keeps the cards it has while a new option's card is read", async () => {
    const scorecard = vi.fn((variantId: string) => Promise.resolve(wire(variantId)));
    const { result, rerender } = mount(scorecard, [key("v1")]);
    await settle();
    rerender({ keys: [key("v1"), key("v2")] });
    expect(result.current.v1?.snapshot?.variant_id).toBe("v1");
    await settle();
    expect(Object.keys(result.current).sort()).toEqual(["v1", "v2"]);
  });
});

describe("what the agent assumed", () => {
  const assumedRow = {
    kind: "assumed" as const,
    label: "assumed by the agent, no verdict" as const,
    statement: "Mass at most 120 g",
    why: "a light part prints fast",
    check_id: "mass",
    instance: "",
    values: [{ measure: "mass", assumed: { magnitude: 120, unit: "g" }, measured: { magnitude: 0.2, unit: "kg" } }],
  };

  it("lists the measure beside the assumed value and counts as neither a pass nor a fail", () => {
    const plain = restore(snapshot("v1", [], [massResult()]));
    const held = restore({ ...snapshot("v1", [], [massResult()]), assumptions: [assumedRow] });
    expect(assumedOf(plain)).toEqual([]);
    expect(assumedOf(held)).toEqual([
      {
        key: "assumed:0",
        label: "Mass at most 120 g",
        why: "a light part prints fast",
        values: [{ measure: "mass", assumed: "120 g", measured: "200 g" }],
      },
    ]);
    expect(summaryOf({ snapshot: held })).toEqual(summaryOf({ snapshot: plain }));
  });

  it("never lists a result that read an assumed load as a check that passed", () => {
    const judged = { ...massResult(), check_id: "fea", instance: "load-1" };
    const assumedLoad = { ...assumedRow, check_id: "fea", instance: "load-1", values: [] };
    const plain = restore(snapshot("v1", [], [massResult(), judged]));
    const held = restore({ ...snapshot("v1", [], [massResult(), feaMeasureOnly("load-1")]), assumptions: [assumedLoad] });
    expect(linesOf(plain).also.map((one) => one.key)).toEqual(["check:mass:", "check:fea:load-1"]);
    expect(linesOf(held).also.map((one) => one.key)).toEqual(["check:mass:"]);
    expect(summaryOf({ snapshot: held })).toEqual(summaryOf({ snapshot: restore(snapshot("v1", [], [massResult()])) }));
  });
});

describe("what waits for the person's Confirm", () => {
  const awaitingRow = {
    kind: "awaiting" as const,
    label: "waiting for your Confirm, no verdict" as const,
    requirement_id: "r1",
    statement: "Mass at most 30 g",
    check_id: "mass",
    instance: "",
    values: [{ measure: "mass", proposed: { magnitude: 30, unit: "g" }, measured: { magnitude: 0.2, unit: "kg" } }],
  };

  it("lists the measure beside the stated target and counts as neither a pass nor a fail", () => {
    const plain = restore(snapshot("v1", [], [massResult()]));
    const held = restore({ ...snapshot("v1", [], [massResult()]), awaiting: [awaitingRow] });
    expect(awaitingOf(plain)).toEqual([]);
    expect(awaitingOf(held)).toEqual([
      { key: "awaiting:r1", label: "Mass at most 30 g", values: [{ measure: "mass", target: "30 g", measured: "200 g" }] },
    ]);
    expect(summaryOf({ snapshot: held })).toEqual(summaryOf({ snapshot: plain }));
  });

  it("never lists a result that read a load awaiting Confirm as a check that passed", () => {
    const waitingLoad = { ...awaitingRow, check_id: "fea", instance: "load-1", values: [] };
    const held = restore({ ...snapshot("v1", [], [massResult(), feaMeasureOnly("load-1")]), awaiting: [waitingLoad] });
    expect(linesOf(held).also.map((one) => one.key)).toEqual(["check:mass:"]);
  });
});

describe("linesOf holes", () => {
  const holes = (sizes: number[], verdict: DoneCheck["verdict"] = "pass"): DoneCheck => ({
    ...massResult(),
    check_id: "holes",
    verdict,
    measured: [
      { name: "hole_count", value: { magnitude: sizes.length, unit: "dimensionless" } },
      ...sizes.map((magnitude, at) => ({ name: `hole_diameter:${String(at)}`, value: { magnitude, unit: "mm" } })),
    ],
  });
  const lineOf = (result: DoneCheck) => linesOf(restore(snapshot("v1", [], [result]))).also[0];

  it("shows the count and every diameter beside the Holes line", () => {
    expect(lineOf(holes([5.5, 5.5]))?.value).toBe("2 holes: 5.5, 5.5 mm");
    expect(lineOf(holes([4.2]))?.value).toBe("1 hole: 4.2 mm");
    expect(lineOf(holes([]))?.value).toBe("no round holes");
  });

  it("keeps the diameters of a part the check could not fully read, with status unknown", () => {
    const line = lineOf(holes([5.5], "unknown"));
    expect(line?.value).toBe("1 hole: 5.5 mm");
    expect(line?.status).toBe("unknown");
    expect(line?.label).toBe("Holes");
  });
});

describe("passedExtents", () => {
  const extents = (verdict: "pass" | "fail" | "unknown", names = ["x", "y", "z"], unit = "mm"): DoneCheck => ({
    ...massResult(),
    check_id: "extents",
    verdict,
    measured: names.map((axis, at) => ({ name: `extent:${axis}`, value: { magnitude: [60.04, 40, 70][at] ?? 0, unit } })),
  });
  const card = (...results: Scorecard["results"]) => snapshot("v1", [], results);

  it("gives the check's three numbers as the Size row writes them", () => {
    expect(passedExtents(card(extents("pass")))).toEqual({ x: "60 mm", y: "40 mm", z: "70 mm" });
  });

  it("gives nothing for a result that failed, is unknown, is pending, is missing or is incomplete", () => {
    expect(passedExtents(card(extents("fail")))).toBeNull();
    expect(passedExtents(card(extents("unknown")))).toBeNull();
    expect(passedExtents(card({ ...feaPending(), check_id: "extents" }))).toBeNull();
    expect(passedExtents(card(massResult()))).toBeNull();
    expect(passedExtents(card(extents("pass", ["x", "y"])))).toBeNull();
    expect(passedExtents(card(extents("pass", ["x", "y", "z"], "m")))).toBeNull();
    expect(passedExtents(null)).toBeNull();
  });
});

describe("the reason on a requirement row", () => {
  const bent = "the part bends 5.6 mm under this load, over 5% of its 100 mm size; make it stiffer";
  const fea = (verdict: "pass" | "unknown", reason: string): DoneCheck => ({ ...massResult(), check_id: "fea", verdict, reason });
  const row = (verdict: "pass" | "unknown", reason: string) => {
    const done = snapshot("v1", [{ ...deflectionDone(), verdict: verdict === "pass" ? "fail" : "unknown", reason: "The scorecard's reason." }], [fea(verdict, reason)]);
    return linesOf(restore(done)).asked[0]?.why;
  };

  it("adds the deciding check's own reason when that check did not pass, since the check has no row", () => {
    expect(row("unknown", bent)).toBe("The scorecard's reason. The part bends 5.6 mm under this load, over 5% of its 100 mm size; make it stiffer.");
  });

  it("is the scorecard's alone when the check passed and measured", () => {
    expect(row("pass", "solved at 2 mm and 1.3 mm")).toBe("The scorecard's reason.");
  });
});

describe("the specimens behind a strength", () => {
  const fea = (specimen: Specimen): DoneCheck => ({
    ...massResult(),
    check_id: "fea",
    reads: [
      { kind: "cited", field: "elastic_modulus" },
      { kind: "cited", field: "yield_strength", specimen },
    ],
  });
  const comparing = (measure: string, requirement_id: string): Checked => {
    const base = deflectionDone();
    return { ...base, requirement_id, comparisons: base.comparisons.map((one) => ({ ...one, measure })) };
  };
  const rows = (specimen: Specimen) => linesOf(restore(snapshot("v1", [comparing("safety_factor", "r2"), comparing("max_displacement", "r3")], [fea(specimen)]))).asked;

  it("are stated beside a safety factor verdict, and not beside a deflection one, which reads no strength", () => {
    expect(rows({ form: "printed", direction: "X-Y" }).map((one) => one.specimen)).toEqual(["strength of prints pulled in the build plane (X-Y), not across layers", undefined]);
  });

  it("say the temper of a metal, or that its page states none", () => {
    expect(rows({ form: "wrought", condition: "T6, T651" })[0]?.specimen).toBe("strength of wrought metal, T6, T651");
    expect(rows({ form: "wrought", condition: null })[0]?.specimen).toBe("strength of wrought metal, temper not stated");
  });

  it("are stated on the check's own row when no requirement covers it", () => {
    const { also } = linesOf(restore(snapshot("v1", [], [fea({ form: "sheet" })])));
    expect(also.find((one) => one.key.startsWith("check:fea"))?.specimen).toBe("strength of plastic sheet, not printed");
  });
});
