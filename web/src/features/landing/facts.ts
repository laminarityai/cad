import data from "./facts.json";

export type Source =
  | { kind: "survey" | "study"; label: string; url: string }
  | { kind: "repo"; label: string; measure: "checks" | "options" | "materials" };

export interface Fact {
  id: string;
  value: string;
  claim: string;
  source: Source;
}

export const FACTS: readonly Fact[] = data.facts as Fact[];

export function fact(id: string): Fact {
  const found = FACTS.find((one) => one.id === id);
  if (!found) throw new Error(`landing: no fact named ${id}`);
  return found;
}

/** The numbers a string writes, such as 89%, 50 or 3. A digit that is part of a word, such as 3MF or M5, is not one. */
export function numbersIn(text: string): string[] {
  return text.match(/(?<![\w.])\d+(?:[.,]\d+)*%?(?!\w)/g) ?? [];
}
