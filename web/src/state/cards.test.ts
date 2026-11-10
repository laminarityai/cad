import { describe, expect, it } from "vitest";
import { cardsReducer, cardsStart } from "./cards";
import { massResult, mass, snapshot } from "@/test/fixtures";

const card = (variant: string) => snapshot(variant, [mass("pass")], [massResult()]);

describe("cardsReducer", () => {
  it("keeps the first snapshot's slot on its variant", () => {
    let state = cardsReducer(cardsStart, { type: "retarget", slot: 1, variantId: "v1" });
    state = cardsReducer(state, { type: "snapshot", slot: 1, snapshot: card("v1") });
    expect(state[1]?.snapshot?.variant_id).toBe("v1");
  });

  it("ignores a snapshot from a variant the slot no longer shows", () => {
    let state = cardsReducer(cardsStart, { type: "retarget", slot: 1, variantId: "v2" });
    state = cardsReducer(state, { type: "snapshot", slot: 1, snapshot: card("v1") });
    expect(state[1]?.snapshot).toBeNull();
  });

  it("carries the last snapshot of the earlier revision as previous when a slot is retargeted", () => {
    let state = cardsReducer(cardsStart, { type: "retarget", slot: 1, variantId: "v1" });
    const before = card("v1");
    state = cardsReducer(state, { type: "snapshot", slot: 1, snapshot: before });
    state = cardsReducer(state, { type: "retarget", slot: 1, variantId: "v2" });
    expect(state[1]).toMatchObject({ variantId: "v2", snapshot: null, previous: before, connection: "connecting" });
  });

  it("does not change state when retargeted to the same variant", () => {
    const state = cardsReducer(cardsStart, { type: "retarget", slot: 1, variantId: "v1" });
    expect(cardsReducer(state, { type: "retarget", slot: 1, variantId: "v1" })).toBe(state);
  });

  it("ignores connection and refusal news from an old variant", () => {
    const state = cardsReducer(cardsStart, { type: "retarget", slot: 1, variantId: "v2" });
    expect(cardsReducer(state, { type: "connection", slot: 1, variantId: "v1", connection: "live" })).toBe(state);
    expect(cardsReducer(state, { type: "refused", slot: 1, variantId: "v1", reason: "x" })).toBe(state);
  });

  it("drops slots that left the set", () => {
    let state = cardsReducer(cardsStart, { type: "retarget", slot: 1, variantId: "v1" });
    state = cardsReducer(state, { type: "retarget", slot: 2, variantId: "v2" });
    state = cardsReducer(state, { type: "drop", keep: [2] });
    expect(Object.keys(state)).toEqual(["2"]);
  });
});
