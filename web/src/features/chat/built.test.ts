import { describe, expect, it } from "vitest";
import { runningRun } from "@/test/fakes";
import { buildOf } from "./built";

const standing = (revision: number, built: boolean) => ({ revision, variant_id: `v${String(revision)}`, code_sha256: String(revision).repeat(64), built, marks: [] });

const revised = (revision: number | null) => {
  const run = runningRun(0);
  return JSON.stringify({ ...run, revision, state: { ...run.state, history: [standing(1, false), standing(2, true)] } });
};

describe("buildOf for auto_revise", () => {
  it("reads the revision the call's code built as, not the newest one", () => {
    expect(buildOf("auto_revise", revised(1))).toBe("failed");
    expect(buildOf("auto_revise", revised(2))).toBe("built");
  });

  it("is unread when the result names no revision it can find", () => {
    expect(buildOf("auto_revise", revised(null))).toBe("unread");
  });
});
