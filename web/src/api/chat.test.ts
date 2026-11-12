import { afterEach, describe, expect, it, vi } from "vitest";
import { httpChat } from "./chat";

const JSON_ACCEPT = { accept: "application/json" };
const JSON_BODY = { accept: "application/json", "content-type": "application/json" };

function reply(status = 200, body: unknown = {}) {
  const fetcher = vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status })));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("httpChat requests", () => {
  it("makes a conversation, with or without a project", async () => {
    const fetcher = reply();
    await httpChat.create();
    await httpChat.create("p1");
    expect(fetcher.mock.calls).toEqual([
      ["/v1/conversations", { method: "POST", credentials: "same-origin", headers: JSON_BODY, body: "{}" }],
      ["/v1/conversations", { method: "POST", credentials: "same-origin", headers: JSON_BODY, body: '{"project_id":"p1"}' }],
    ]);
  });

  it("reads one conversation", async () => {
    const fetcher = reply();
    await httpChat.read("c 1");
    expect(fetcher.mock.calls).toEqual([["/v1/conversations/c%201", { method: "GET", credentials: "same-origin", headers: JSON_ACCEPT }]]);
  });

  it("sends a message with its selection only when there is one", async () => {
    const fetcher = reply();
    await httpChat.send("c1", "thicker");
    await httpChat.send("c1", "thicker", { variant_id: "v1", part: true });
    expect(fetcher.mock.calls).toEqual([
      ["/v1/conversations/c1/messages", { method: "POST", credentials: "same-origin", headers: JSON_BODY, body: '{"text":"thicker"}' }],
      ["/v1/conversations/c1/messages", { method: "POST", credentials: "same-origin", headers: JSON_BODY, body: '{"text":"thicker","selection":{"variant_id":"v1","part":true}}' }],
    ]);
  });

  it("stops a run with a bodiless POST", async () => {
    const fetcher = reply();
    await httpChat.stop("run 1");
    expect(fetcher.mock.calls).toEqual([
      ["/v1/auto/run%201/stop", { method: "POST", credentials: "same-origin", headers: JSON_ACCEPT }],
    ]);
  });
});

describe("httpChat.follow", () => {
  it("opens the stream after the last seen event, reports the link and hands over each event", async () => {
    const frame = 'id: 4\nevent: agent\ndata: {"kind":"agent","text":"hi"}\n\n';
    const fetcher = vi.fn(() => Promise.resolve(new Response(frame, { status: 200 })));
    vi.stubGlobal("fetch", fetcher);
    const links: string[] = [];
    const events: [number, unknown][] = [];
    const unfollow = httpChat.follow("c 1", 3, {
      onEvent: (seq, event) => events.push([seq, event]),
      onLink: (link) => links.push(link),
    });
    await vi.waitFor(() => {
      expect(events).toEqual([[4, { kind: "agent", text: "hi" }]]);
    });
    unfollow();
    expect(fetcher.mock.calls[0]).toEqual([
      "/v1/conversations/c%201/stream?after=3",
      { credentials: "same-origin", headers: { accept: "text/event-stream" }, signal: expect.any(AbortSignal) as AbortSignal },
    ]);
    expect(links.slice(0, 2)).toEqual(["connecting", "live"]);
  });

  it("says signed out for a 401 and not found for a 404, and stops", async () => {
    for (const [status, link] of [
      [401, "signed_out"],
      [404, "not_found"],
    ] as const) {
      const fetcher = vi.fn(() => Promise.resolve(new Response("", { status })));
      vi.stubGlobal("fetch", fetcher);
      const links: string[] = [];
      httpChat.follow("c1", 0, { onEvent: () => undefined, onLink: (one) => links.push(one) });
      await vi.waitFor(() => {
        expect(links).toEqual(["connecting", link]);
      });
      expect(fetcher).toHaveBeenCalledTimes(1);
    }
  });
});
