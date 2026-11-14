import { QuestionCard } from "@/components/ui/question-card";
import type { Line } from "./state";
import { answerText, askedOf } from "./questions";

export function Questions({ lines, onSend }: { lines: readonly Line[]; onSend: (text: string) => Promise<void> }) {
  const asked = askedOf(lines);
  if (asked === null) return null;
  return <QuestionCard key={asked.callId} questions={asked.questions} onSend={(answers) => onSend(answerText(asked.questions, answers))} />;
}
