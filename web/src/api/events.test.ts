import { afterEach, describe, expect, it, vi } from "vitest";
import { eventsUrl, serverEvents, type CardHandlers } from "./events";
import { massResult, mass, snapshot } from "@/test/fixtures";

class FakeSource {
  static last: FakeSource | null = null;
  static readonly CLOSED = 2;
  readyState = 0;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readonly listeners = new Map<string, (event: { data: string }) => void>();
  closed = false;

  constructor(
    readonly url: string,
    readonly init: { withCredentials: boolean },
  ) {
    FakeSource.last = this;
  }

  addEventListener(name: string, listener: (event: { data: string }) => void): void {
    this.listeners.set(name, listener);
  }

  close(): void {
    this.closed = true;
    this.readyState = FakeSource.CLOSED;
  }
}

function handlers(): CardHandlers & { seen: string[] } {
  const seen: string[] = [];
  return {
    seen,
    onSnapshot: (one) => seen.push(`snapshot:${one.etag}`),
    onConnection: (one) => seen.push(`connection:${one}`),
    onRefused: (reason) => seen.push(`refused:${reason}`),
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  FakeSource.last = null;
});

describe("serverEvents", () => {
  it("asks for the variant's stream with the material and the brief, sending the cookie", () => {
    vi.stubGlobal("EventSource", FakeSource);
    serverEvents.open({ variantId: "v 1", materialKey: "pla", briefId: "b1" }, handlers());
    expect(FakeSource.last?.url).toBe(eventsUrl({ variantId: "v 1", materialKey: "pla", briefId: "b1" }));
    expect(FakeSource.last?.url).toBe("/v1/variants/v%201/events?material_key=pla&brief_id=b1");
    expect(FakeSource.last?.init.withCredentials).toBe(true);
  });

  it("passes each scorecard event on as a whole snapshot and reports the connection", () => {
    vi.stubGlobal("EventSource", FakeSource);
    const seen = handlers();
    serverEvents.open({ variantId: "v1", materialKey: "pla", briefId: "b1" }, seen);
    const source = FakeSource.last;
    source?.onopen?.();
    source?.listeners.get("scorecard")?.({ data: JSON.stringify(snapshot("v1", [mass("pass")], [massResult()], "e2")) });
    expect(seen.seen).toEqual(["connection:connecting", "connection:live", "snapshot:e2"]);
  });

  it("closes the source on a refused event and when the caller closes it", () => {
    vi.stubGlobal("EventSource", FakeSource);
    const seen = handlers();
    const close = serverEvents.open({ variantId: "v1", materialKey: "pla", briefId: "b1" }, seen);
    FakeSource.last?.listeners.get("refused")?.({ data: "no such variant" });
    expect(FakeSource.last?.closed).toBe(true);
    expect(seen.seen).toContain("refused:no such variant");
    close();
  });
});
