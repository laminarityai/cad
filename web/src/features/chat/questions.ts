import type { Line } from "./state";

export interface Question {
  question: string;
  default: string;
  why: string;
  suggestions: readonly string[];
}

export interface Asked {
  callId: string;
  questions: readonly Question[];
}

export const DEFAULTS = "Build it with your defaults.";
export const REST = "Use your defaults for the rest.";

function parsed(text: string): readonly Question[] {
  try {
    const said = (JSON.parse(text) as { questions?: unknown } | null)?.questions;
    return Array.isArray(said) ? (said as Question[]) : [];
  } catch {
    return [];
  }
}

/** The questions the agent asked that the person has not answered yet: the newest ask_questions
 * that returned, with no message from the person after it. */
export function askedOf(lines: readonly Line[]): Asked | null {
  const at = lines.findLastIndex((line) => line.kind === "tool" && line.name === "ask_questions" && line.result !== null && !line.result.isError);
  const line = lines[at];
  if (line?.kind !== "tool" || line.result === null) return null;
  if (lines.slice(at + 1).some((one) => one.kind === "user")) return null;
  const questions = parsed(line.result.text);
  return questions.length === 0 ? null : { callId: line.callId, questions };
}

/** The person's answer as one chat message: a "question: answer" line for each they answered, and
 * the defaults for the rest. */
export function answerText(questions: readonly Question[], answers: readonly string[]): string {
  const said = questions.flatMap((one, at) => {
    const answer = answers[at]?.trim() ?? "";
    return answer === "" ? [] : [`${one.question}: ${answer}`];
  });
  if (said.length === 0) return DEFAULTS;
  return said.length === questions.length ? said.join("\n") : [...said, REST].join("\n");
}
