import { afterEach, describe, expect, it, vi } from "vitest";
import { httpApi, NotFound, Refused, SignedOut } from "./client";

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
    expect(fetcher.mock.calls).toEqual([[url, JSON_GET]]);
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
});
