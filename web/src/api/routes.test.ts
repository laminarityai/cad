import { describe, expect, it } from "vitest";
import { request } from "./client";

/** `tsc` is the test: each `@ts-expect-error` line fails the build when the client stops refusing it. */
function mistakes() {
  // @ts-expect-error a route the server does not have
  void request("get", "/v1/nope");
  // @ts-expect-error a path part the route does not have
  void request("get", "/v1/projects/{project_id}", { path: { projectid: "p1" } });
  // @ts-expect-error a route with a path part needs it
  void request("get", "/v1/projects/{project_id}");
  // @ts-expect-error a method the route does not have
  void request("post", "/v1/projects");
  // @ts-expect-error a query parameter the route does not have
  void request("get", "/v1/variants/{variant_id}/scorecard", { path: { variant_id: "v1" }, query: { brief: "b1" } });
  // @ts-expect-error a body the route does not take
  void request("put", "/v1/conversations/{conversation_id}/mode", { path: { conversation_id: "c1" }, body: { mode: "nope" } });
}

describe("request", () => {
  it("only takes the routes, methods, path parts, queries and bodies the server's types describe", () => {
    expect(typeof mistakes).toBe("function");
  });
});
