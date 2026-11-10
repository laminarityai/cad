import type {
  Comparison,
  Measured,
  RequirementResult,
  Verdict,
} from "@/api/types";
import type { DoneCheck, RunningCheck, Scorecard } from "@/api/snapshot";

/** A row of the scorecard. Only a settled row carries a verdict, so no pending row can be drawn
 * in a verdict colour. */
export type Row =
  | { kind: "pending"; key: string; label: string; check: string }
  | {
      kind: "settled";
      key: string;
      label: string;
      check: string;
      verdict: Verdict;
      researched: boolean;
      measures: string[];
      note: string;
    }
  | { kind: "unverified"; key: string; label: string };

const isPending = (one: DoneCheck | RunningCheck): one is RunningCheck => "kind" in one;

export interface Rows {
  requirements: Row[];
  checks: Row[];
}

export function formatQuantity(quantity: Measured): string {
  return `${String(Number(quantity.magnitude.toPrecision(4)))} ${quantity.unit}`;
}

const COMPARATOR = { at_most: "≤", at_least: "≥" } as const;

function measureOf(results: Scorecard["results"], checkId: string, name: string) {
  for (const result of results) {
    if (isPending(result) || result.check_id !== checkId) continue;
    const found = result.measured.find((one) => one.name === name);
    if (found) return found.value;
  }
  return null;
}

function comparisonText(results: Scorecard["results"], checkId: string, one: Comparison) {
  const measured = measureOf(results, checkId, one.measure);
  const limit = `${COMPARATOR[one.comparator]} ${formatQuantity(one.limit)}`;
  return measured ? `${one.measure} ${formatQuantity(measured)} ${limit}` : `${one.measure} ${limit}`;
}

/** A verdict this page does not know reads as unknown, so it still counts and is drawn. */
function verdictOf(verdict: string): Verdict {
  return verdict === "pass" || verdict === "fail" ? verdict : "unknown";
}

function requirementRow(results: Scorecard["results"], one: RequirementResult): Row {
  const key = `req:${one.requirement_id}`;
  const kind: string = one.kind;
  switch (one.kind) {
    case "waiting":
      return { kind: "pending", key, label: one.statement, check: one.check_id };
    case "unverified":
      return { kind: "unverified", key, label: one.statement };
    case "checked":
      return {
        kind: "settled",
        key,
        label: one.statement,
        check: one.check_id,
        verdict: verdictOf(one.verdict),
        researched: one.basis === "researched",
        measures: one.comparisons.map((c) => comparisonText(results, one.check_id, c)),
        note: one.reason,
      };
    default:
      return {
        kind: "settled",
        key,
        label: (one as { statement?: string }).statement ?? key,
        check: "",
        verdict: "unknown",
        researched: false,
        measures: [],
        note: `This page does not know a requirement result of kind ${kind}.`,
      };
  }
}

function checkRow(one: DoneCheck | RunningCheck): Row {
  const label = one.instance ? `${one.check_id} ${one.instance}` : one.check_id;
  const key = `check:${one.check_id}:${one.instance}`;
  if (isPending(one)) return { kind: "pending", key, label, check: one.check_id };
  return {
    kind: "settled",
    key,
    label,
    check: one.check_id,
    verdict: verdictOf(one.verdict),
    researched: one.reads.some((read) => read.kind === "researched"),
    measures: one.measured.map((m) => `${m.name} ${formatQuantity(m.value)}`),
    note: one.reason,
  };
}

export function rowsOf(snapshot: Scorecard): Rows {
  const against = snapshot.basis.kind === "against_brief" ? snapshot.basis : null;
  return {
    requirements: against ? against.requirements.map((one) => requirementRow(snapshot.results, one)) : [],
    checks: snapshot.results.map(checkRow),
  };
}

/** What a settled row said, to show beside its pending successor as the "before" text. */
export function ghostOf(row: Row): string | null {
  return row.kind === "settled" && row.measures.length > 0 ? row.measures.join("; ") : null;
}

export function ghostsOf(snapshot: Scorecard | null): Record<string, string> {
  if (!snapshot) return {};
  const found: Record<string, string> = {};
  const { requirements, checks } = rowsOf(snapshot);
  for (const row of [...requirements, ...checks]) {
    const ghost = ghostOf(row);
    if (ghost) found[row.key] = ghost;
  }
  return found;
}

export interface Tally {
  pass: number;
  fail: number;
  unknown: number;
  pending: number;
  unverified: number;
}

export function tally(rows: readonly Row[]): Tally {
  const found: Tally = { pass: 0, fail: 0, unknown: 0, pending: 0, unverified: 0 };
  for (const row of rows) {
    if (row.kind === "settled") found[row.verdict] += 1;
    else found[row.kind] += 1;
  }
  return found;
}

/** The rows a card shows before its first snapshot arrives for a rebuilt slot: every row of the
 * revision before, pending. */
export function pendingFrom(rows: Rows): Rows {
  const hold = (row: Row): Row =>
    row.kind === "settled" ? { kind: "pending", key: row.key, label: row.label, check: row.check } : row;
  return { requirements: rows.requirements.map(hold), checks: rows.checks.map(hold) };
}
