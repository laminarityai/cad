import { QuestionCard } from "@/components/ui/question-card";
import type { Line } from "./state";
import { answerText, askedOf } from "./questions";

/** The card for the questions the agent asked and the person has not answered. Its answer is an
 * ordinary chat message. */
export function Questions({ lines, onSend }: { lines: readonly Line[]; onSend: (text: string) => Promise<void> }) {
  const asked = askedOf(lines);
  if (asked === null) return null;
  return <QuestionCard key={asked.callId} questions={asked.questions} onSend={(answers) => onSend(answerText(asked.questions, answers))} />;
}
