import { autoRunOf } from "@/features/auto/run";

export type Build = "built" | "failed" | "unread";

const BUILDS: ReadonlySet<string> = new Set(["build_variant", "auto_revise"]);

function outcomeOf(text: string): unknown {
  try {
    return (JSON.parse(text) as { outcome?: { kind?: unknown } } | null)?.outcome?.kind;
  } catch {
    return undefined;
  }
}

/** Whether a build tool's result says the code built. A result the server cut too long to parse is
 * `unread`, so the page never says built without reading it. Null for a tool that builds nothing.
 * `settling` comes back only after a build that built, while its checks still run. */
export function buildOf(name: string, text: string): Build | null {
  if (!BUILDS.has(name)) return null;
  if (name === "build_variant") {
    const kind = outcomeOf(text);
    return typeof kind !== "string" ? "unread" : kind === "built" ? "built" : "failed";
  }
  const run = autoRunOf(text);
  if (run === null) return "unread";
  if (run.settling) return "built";
  const last = run.state.history.at(-1);
  return last === undefined ? "unread" : last.built ? "built" : "failed";
}
