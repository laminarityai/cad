import { useEffect, useState } from "react";
import { useServices } from "@/app/context";
import { restore, type DoneCheck, type RunningCheck, type Scorecard } from "@/api/snapshot";
import type { Source } from "@/api/types";

const POLL_MS = 1500;

export interface Card {
  snapshot: Scorecard | null;
}

export interface CardKey {
  variantId: string;
  materialKey: string | null;
  briefId: string;
}

/** Polls each card instead of streaming it: a browser holds six connections per host, and the
 * chat stream and the meshes need theirs. */
export function useCards(keys: CardKey[]): Record<string, Card> {
  const { api } = useServices();
  const [cards, setCards] = useState<Record<string, Card>>({});
  const joined = keys.map((one) => `${one.variantId}|${one.materialKey ?? ""}|${one.briefId}`).join(",");
  useEffect(() => {
    let live = true;
    const entries = [...new Set(joined.split(",").filter(Boolean))];
    const once = async () => {
      await Promise.all(
        entries.map(async (entry) => {
          const [variantId = "", materialKey = "", briefId = ""] = entry.split("|");
          try {
            const wire = await api.scorecard(variantId, briefId, materialKey === "" ? null : materialKey);
            if (live)
              setCards((now) => ({
                ...now,
                [variantId]: { snapshot: restore(wire) },
              }));
          } catch {
            if (live)
              setCards((now) => ({
                ...now,
                [variantId]: { snapshot: now[variantId]?.snapshot ?? null },
              }));
          }
        }),
      );
    };
    void once();
    const timer = setInterval(() => void once(), POLL_MS);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [api, joined]);
  return cards;
}

function short(statement: string): string {
  const first = statement.split(/(?<=[a-z0-9)])[.(]\s/)[0] ?? statement;
  return first.length > 70 ? `${first.slice(0, 68)}…` : first;
}

export type Status = "pass" | "fail" | "unknown" | "running" | "unchecked" | "researched";

export interface Line {
  key: string;
  label: string;
  status: Status;
  value: string;
  why: string;
  formula: string;
  sources: Source[];
}

const CHECK_NAMES: Record<string, string> = {
  closed_solid: "One solid",
  interference: "No parts overlap",
  mass: "Mass",
  extents: "Size",
  fit: "Fit",
  fea: "Stiffness",
  holes: "Holes",
};

const isRunning = (one: DoneCheck | RunningCheck): one is RunningCheck => "kind" in one;

function num(magnitude: number): string {
  return String(Number(magnitude.toPrecision(3)));
}

function valueOf(result: DoneCheck | undefined): string {
  if (!result) return "";
  const by = (name: string) => result.measured.find((one) => one.name === name)?.value;
  if (result.check_id === "mass") {
    const mass = by("mass");
    if (mass) return mass.unit === "kg" ? `${num(mass.magnitude * 1000)} g` : `${num(mass.magnitude)} ${mass.unit}`;
  }
  if (result.check_id === "extents") {
    const edges = ["x", "y", "z"].map((axis) => by(`extent:${axis}`)).filter((one) => one !== undefined);
    if (edges.length === 3) return `${edges.map((one) => num(one.magnitude)).join(" × ")} mm`;
  }
  if (result.check_id === "closed_solid") {
    const solids = by("solids");
    if (solids && solids.magnitude !== 1) return `${num(solids.magnitude)} solids`;
  }
  return "";
}

function statusOf(verdict: string, researched: boolean): Status {
  if (verdict === "pass") return researched ? "researched" : "pass";
  return verdict === "fail" ? "fail" : "unknown";
}

export function linesOf(snapshot: Scorecard): { asked: Line[]; also: Line[] } {
  const results = snapshot.results;
  const done = (id: string) => results.find((one): one is DoneCheck => !isRunning(one) && one.check_id === id);
  const running = (id: string) => results.some((one) => isRunning(one) && one.check_id === id);
  const asked: Line[] = [];
  const covered = new Set<string>();
  if (snapshot.basis.kind === "against_brief") {
    for (const one of snapshot.basis.requirements) {
      const key = `req:${one.requirement_id}`;
      if (one.kind === "unverified") {
        asked.push({
          key,
          label: short(one.statement),
          status: "unchecked",
          value: "",
          why: one.statement,
          formula: "",
          sources: [],
        });
        continue;
      }
      covered.add(one.check_id);
      const result = done(one.check_id);
      if (one.kind === "waiting" || running(one.check_id)) {
        asked.push({
          key,
          label: short(one.statement),
          status: "running",
          value: "",
          why: "",
          formula: "",
          sources: [],
        });
        continue;
      }
      const researched = "basis" in one && one.basis === "researched";
      asked.push({
        key,
        label: short(one.statement),
        status: statusOf("verdict" in one ? one.verdict : "unknown", researched),
        value: valueOf(result),
        why: "reason" in one ? one.reason : "",
        formula: result?.formula ?? "",
        sources: result?.sources ?? [],
      });
    }
  }
  const also: Line[] = results
    .filter((one) => !covered.has(one.check_id))
    .map((one) => {
      const label = CHECK_NAMES[one.check_id] ?? one.check_id.replace(/_/g, " ");
      if (isRunning(one))
        return {
          key: `check:${one.check_id}`,
          label,
          status: "running" as const,
          value: "",
          why: "",
          formula: one.formula,
          sources: one.sources,
        };
      return {
        key: `check:${one.check_id}:${one.instance}`,
        label,
        status: statusOf(
          one.verdict,
          one.reads.some((read) => read.kind === "researched"),
        ),
        value: valueOf(one),
        why: one.reason,
        formula: one.formula,
        sources: one.sources,
      };
    });
  return { asked, also };
}

export function summaryOf(card: Card | undefined): {
  status: Status | "none";
  text: string;
} {
  if (!card?.snapshot) return { status: "none", text: card ? "Checking" : "" };
  const { asked, also } = linesOf(card.snapshot);
  const all = [...asked, ...also];
  if (all.some((one) => one.status === "running")) return { status: "running", text: "Checking" };
  const fails = all.filter((one) => one.status === "fail").length;
  if (fails > 0)
    return {
      status: "fail",
      text: `${String(fails)} fail${fails === 1 ? "s" : ""}`,
    };
  if (all.some((one) => one.status === "unknown")) return { status: "unknown", text: "Unknowns" };
  return { status: "pass", text: "All pass" };
}

export function sourcesOf(cards: Record<string, Card>): Source[] {
  const seen = new Map<string, Source>();
  for (const card of Object.values(cards)) {
    for (const result of card.snapshot?.results ?? []) for (const one of result.sources) seen.set(one.url, one);
  }
  return [...seen.values()];
}
