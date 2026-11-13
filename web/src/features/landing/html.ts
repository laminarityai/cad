/** A string that is already HTML. Every other value that `html` meets is escaped. */
export class Raw {
  constructor(readonly text: string) {}
  toString(): string {
    return this.text;
  }
}

export const raw = (text: string): Raw => new Raw(text);

export function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

type Value = string | number | Raw | readonly Value[] | null | undefined | false;

function one(value: Value): string {
  if (value === null || value === undefined || value === false) return "";
  if (value instanceof Raw) return value.text;
  if (Array.isArray(value)) return (value as readonly Value[]).map(one).join("");
  return escapeHtml(String(value));
}

/** Tagged template that escapes what it interpolates and passes `raw(...)` and nested `html` through. */
export function html(strings: TemplateStringsArray, ...values: Value[]): Raw {
  return new Raw(strings.reduce((out, part, at) => out + part + (at < values.length ? one(values[at]) : ""), ""));
}
