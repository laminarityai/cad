import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NotFound, SignedOut } from "@/api/client";
import { useResource, useResources } from "./resource";

const settle = () => act(() => vi.advanceTimersByTimeAsync(0));
const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useResource", () => {
  it("loads once per key and says what the load came to", async () => {
    const load = vi.fn(() => Promise.resolve("a"));
    const { result } = renderHook(() => useResource(load, "k"));
    expect(result.current.resource).toEqual({ status: "loading" });
    await settle();
    expect(result.current.resource).toEqual({ status: "ok", data: "a" });
    await tick(60_000);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("names a sign-out, a missing thing and any other failure", async () => {
    const outcomes: [unknown, unknown][] = [
      [new SignedOut(), { status: "signed_out" }],
      [new NotFound("x"), { status: "not_found" }],
      [new Error("boom"), { status: "error", message: "boom" }],
      ["odd", { status: "error", message: "the request failed" }],
    ];
    for (const [error, resource] of outcomes) {
      const { result } = renderHook(() => useResource(() => Promise.reject(error as Error), "k"));
      await settle();
      expect(result.current.resource).toEqual(resource);
    }
  });

  it("starts over when the key changes", async () => {
    const load = vi.fn((): Promise<string> => Promise.resolve("first"));
    const { result, rerender } = renderHook(({ key }) => useResource(load, key), { initialProps: { key: "a" } });
    await settle();
    expect(result.current.resource).toEqual({ status: "ok", data: "first" });
    load.mockImplementation(() => Promise.resolve("second"));
    rerender({ key: "b" });
    await settle();
    expect(result.current.resource).toEqual({ status: "ok", data: "second" });
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("follows: loads again followMs after each load ends, and keeps the data when a follow fails", async () => {
    const load = vi
      .fn<() => Promise<string>>()
      .mockResolvedValueOnce("one")
      .mockResolvedValueOnce("two")
      .mockRejectedValueOnce(new Error("restarting"))
      .mockResolvedValue("four");
    const { result } = renderHook(() => useResource(load, "k", 1000));
    await settle();
    expect(result.current.resource).toEqual({ status: "ok", data: "one" });
    await tick(1000);
    expect(result.current.resource).toEqual({ status: "ok", data: "two" });
    await tick(1000);
    expect(load).toHaveBeenCalledTimes(3);
    expect(result.current.resource).toEqual({ status: "ok", data: "two" });
    await tick(1000);
    expect(result.current.resource).toEqual({ status: "ok", data: "four" });
  });

  it("stops following after a sign-out and shows it", async () => {
    const load = vi.fn().mockResolvedValueOnce("one").mockRejectedValueOnce(new SignedOut());
    const { result } = renderHook(() => useResource(load, "k", 1000));
    await settle();
    await tick(1000);
    expect(result.current.resource).toEqual({ status: "signed_out" });
    await tick(10_000);
    expect(load).toHaveBeenCalledTimes(2);
  });

  it("shows a first failure, and retries it when following", async () => {
    const load = vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValue("up");
    const { result } = renderHook(() => useResource(load, "k", 1000));
    await settle();
    expect(result.current.resource).toEqual({ status: "error", message: "down" });
    await tick(1000);
    expect(result.current.resource).toEqual({ status: "ok", data: "up" });
  });

  it("reload reads again at once, and asks that arrive during a read make one more read", async () => {
    let release: () => void = () => undefined;
    const load = vi.fn((): Promise<number> => {
      return new Promise((resolve) => {
        release = () => {
          resolve(load.mock.calls.length);
        };
      });
    });
    const { result } = renderHook(() => useResource(load, "k"));
    await settle();
    expect(load).toHaveBeenCalledTimes(1);
    act(() => {
      release();
    });
    await settle();
    expect(result.current.resource).toEqual({ status: "ok", data: 1 });
    act(() => {
      result.current.reload();
      result.current.reload();
      result.current.reload();
    });
    expect(load).toHaveBeenCalledTimes(2);
    act(() => {
      release();
    });
    await settle();
    expect(load).toHaveBeenCalledTimes(3);
    act(() => {
      release();
    });
    await settle();
    expect(load).toHaveBeenCalledTimes(3);
    expect(result.current.resource).toEqual({ status: "ok", data: 3 });
  });

  it("does not apply a load that ends after the key changed or the page left", async () => {
    let release: (value: string) => void = () => undefined;
    const load = vi.fn((): Promise<string> => new Promise((resolve) => (release = resolve)));
    const { result, unmount } = renderHook(() => useResource(load, "k"));
    await settle();
    unmount();
    release("late");
    await settle();
    expect(result.current.resource).toEqual({ status: "loading" });
  });

  it("reads again when the tab becomes visible, only while following", async () => {
    const load = vi.fn(() => Promise.resolve("x"));
    renderHook(() => useResource(load, "once"));
    await settle();
    document.dispatchEvent(new Event("visibilitychange"));
    await settle();
    expect(load).toHaveBeenCalledTimes(1);
    renderHook(() => useResource(load, "follow", 1000));
    await settle();
    expect(load).toHaveBeenCalledTimes(2);
    document.dispatchEvent(new Event("visibilitychange"));
    await settle();
    expect(load).toHaveBeenCalledTimes(3);
  });
});

describe("useResource keys", () => {
  it("never shows one key's data under another", async () => {
    const seen: unknown[] = [];
    const { rerender } = renderHook(
      ({ key }) => {
        const { resource } = useResource(() => Promise.resolve(key), key);
        seen.push(resource);
        return resource;
      },
      { initialProps: { key: "a" } },
    );
    await settle();
    seen.length = 0;
    rerender({ key: "b" });
    await settle();
    expect(seen[0]).toEqual({ status: "loading" });
    expect(seen[seen.length - 1]).toEqual({ status: "ok", data: "b" });
  });

  it("aborts the signal a load was given when the key changes or the page leaves", async () => {
    const signals: AbortSignal[] = [];
    const load = (signal: AbortSignal) => {
      signals.push(signal);
      return new Promise<string>(() => undefined);
    };
    const { rerender, unmount } = renderHook(({ key }) => useResource(load, key), { initialProps: { key: "a" } });
    await settle();
    rerender({ key: "b" });
    await settle();
    expect(signals.map((one) => one.aborted)).toEqual([true, false]);
    unmount();
    expect(signals[1]?.aborted).toBe(true);
  });
});

describe("useResources", () => {
  it("reads each key once, keeps the data of a key that stays and forgets one that goes", async () => {
    const load = vi.fn((key: string) => Promise.resolve(key.toUpperCase()));
    const { result, rerender } = renderHook(({ keys }) => useResources(keys, load), { initialProps: { keys: ["a", "b", "a"] } });
    await settle();
    expect(result.current.resources).toEqual({ a: { status: "ok", data: "A" }, b: { status: "ok", data: "B" } });
    expect(load).toHaveBeenCalledTimes(2);
    rerender({ keys: ["b", "c"] });
    expect(result.current.resources).toEqual({ b: { status: "ok", data: "B" }, c: { status: "loading" } });
    await settle();
    expect(result.current.resources).toEqual({ b: { status: "ok", data: "B" }, c: { status: "ok", data: "C" } });
  });

  it("follows each key on its own, and a sign-out ends only the key that had it", async () => {
    const calls: string[] = [];
    const load = (key: string) => {
      calls.push(key);
      return key === "gone" && calls.length > 2 ? Promise.reject(new SignedOut()) : Promise.resolve(key);
    };
    const { result } = renderHook(() => useResources(["gone", "stay"], load, 1000));
    await settle();
    await tick(1000);
    expect(result.current.resources.gone).toEqual({ status: "signed_out" });
    expect(result.current.resources.stay).toEqual({ status: "ok", data: "stay" });
    await tick(3000);
    expect(calls.filter((one) => one === "gone")).toHaveLength(2);
    expect(calls.filter((one) => one === "stay")).toHaveLength(5);
  });
});
