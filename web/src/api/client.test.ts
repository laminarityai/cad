import { afterEach, describe, expect, it, vi } from "vitest";
import { httpApi, NotFound, ANSWER_TIMEOUT_MS, Refused, SignedOut } from "./client";

const JSON_GET = { method: "GET", credentials: "same-origin", headers: { accept: "application/json" } };

function reply(status: number, body: unknown = {}) {
  const fetcher = vi.fn(() => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } })));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("httpApi requests", () => {
  const reads: [string, () => Promise<unknown>, string][] = [
    ["projects", () => httpApi.projects(), "/v1/projects"],
    ["project", () => httpApi.project("p 1"), "/v1/projects/p%201"],
    ["brief", () => httpApi.brief("b1"), "/v1/briefs/b1"],
    ["conversation", () => httpApi.conversation("p1"), "/v1/projects/p1/conversation"],
    ["confirmation", () => httpApi.confirmation("p1"), "/v1/projects/p1/confirmation"],
    ["scorecard with a material", () => httpApi.scorecard("v1", "b1", "pla"), "/v1/variants/v1/scorecard?brief_id=b1&material_key=pla"],
    ["scorecard with no material", () => httpApi.scorecard("v1", "b1", null), "/v1/variants/v1/scorecard?brief_id=b1"],
    ["variant set", () => httpApi.variantSet("p1", "b1"), "/v1/projects/p1/briefs/b1/set"],
    ["variant set with a material", () => httpApi.variantSet("p1", "b1", "pla"), "/v1/projects/p1/briefs/b1/set?material_key=pla"],
    ["materials", () => httpApi.materials(), "/v1/materials"],
    ["view", () => httpApi.view("v1"), "/v1/variants/v1"],
    ["mesh", () => httpApi.mesh("/v1/geometry/0123456789ab/v1.json"), "/v1/geometry/0123456789ab/v1.json"],
    ["geometry", () => httpApi.geometry("v1"), "/v1/variants/v1/geometry"],
  ];

  it.each(reads)("%s is one GET with the session cookie", async (_name, call, url) => {
    const fetcher = reply(200);
    await call();
    expect(fetcher.mock.calls).toEqual([[url, { ...JSON_GET, signal: expect.any(AbortSignal) as AbortSignal }]]);
  });

  it("posts a confirmation answer as a form and reads the page's words", async () => {
    const fetcher = vi.fn(() => Promise.resolve(new Response("<html><body><p> Recorded. </p></body></html>", { status: 200, headers: { "content-type": "text/html" } })));
    vi.stubGlobal("fetch", fetcher);
    const answered = await httpApi.answer("p 1", new URLSearchParams({ answer: "confirm" }));
    expect(fetcher.mock.calls).toEqual([
      ["/projects/p%201/confirm", { method: "POST", credentials: "same-origin", headers: { "content-type": "application/x-www-form-urlencoded" }, body: "answer=confirm" }],
    ]);
    expect(answered).toEqual({ status: 200, text: "Recorded." });
  });
});

describe("httpApi answers", () => {
  it("says signed out for a 401, not found for a 404, and the server's words for any other refusal", async () => {
    reply(401);
    await expect(httpApi.projects()).rejects.toBeInstanceOf(SignedOut);
    reply(404);
    await expect(httpApi.project("p1")).rejects.toEqual(new NotFound("/v1/projects/p1"));
    reply(400, { error: "no such slot" });
    await expect(httpApi.projects()).rejects.toEqual(new Refused(400, "no such slot"));
    reply(503, "down");
    await expect(httpApi.projects()).rejects.toEqual(new Refused(503, "HTTP 503"));
  });

  it("carries the kind of refusal the server names", async () => {
    reply(400, { error: "NotScored: variant v1 has no stored check result", kind: "NotScored" });
    await expect(httpApi.scorecard("v1", "b1", null)).rejects.toMatchObject({ status: 400, kind: "NotScored" });
  });
});

describe("a read the server never answers", () => {
  it("fails once the read timeout passes, and not before, so the page stops saying it is reading", async () => {
    vi.useFakeTimers();
    const hung = (_url: string, init: RequestInit) =>
      new Promise<Response>((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => {
          reject(init.signal?.reason as Error);
        });
      });
    vi.stubGlobal("fetch", vi.fn(hung));
    let said: unknown = null;
    void httpApi.scorecard("v1", "b1", null).catch((error: unknown) => {
      said = error;
    });
    await vi.advanceTimersByTimeAsync(ANSWER_TIMEOUT_MS - 1);
    expect(said).toBeNull();
    await vi.advanceTimersByTimeAsync(1);
    expect(said).toBeInstanceOf(Error);
    expect((said as Error).message).toMatch(/did not answer/);
    vi.useRealTimers();
  });
});
