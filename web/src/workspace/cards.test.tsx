import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ServicesProvider } from "@/app/context";
import { FakeChat, FakeEvents, FakeViewer, fakeApi } from "@/test/fakes";
import { massResult, snapshot } from "@/test/fixtures";
import { useCards, type CardKey } from "./cards";

const settle = () => act(() => vi.advanceTimersByTimeAsync(0));
const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

const wire = (variantId: string) => snapshot(variantId, [], [massResult()]);

function mount(scorecard: ReturnType<typeof fakeApi>["scorecard"], initial: CardKey[]) {
  const api = fakeApi([], { scorecard });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <ServicesProvider services={{ api, events: new FakeEvents(), viewer: new FakeViewer(), chat: new FakeChat() }}>{children}</ServicesProvider>
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
