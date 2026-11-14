import type { ReactNode } from "react";
import { CodeBlock } from "@/components/ui/code-block";
import { StreamCaret, StreamWords } from "@/components/ui/stream-text";

function inline(text: string, key: string, streaming: boolean): ReactNode[] {
  const plain = (piece: string, at: string): ReactNode => (streaming ? <StreamWords key={at} text={piece} /> : piece);
  const out: ReactNode[] = [];
  const pattern = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*\s][^*]*\*|\[[^\]]+\]\([^)\s]+\))/g;
  let last = 0;
  let n = 0;
  for (const match of text.matchAll(pattern)) {
    const at = match.index;
    if (at > last) out.push(plain(text.slice(last, at), `${key}-t${String(n)}`));
    const token = match[0];
    const k = `${key}-${String(n++)}`;
    if (token.startsWith("**")) out.push(<strong key={k}>{inline(token.slice(2, -2), k, streaming)}</strong>);
    else if (token.startsWith("`"))
      out.push(
        <code key={k} className="rounded bg-panel-2 px-1 font-mono text-[0.9em]">
          {token.slice(1, -1)}
        </code>,
      );
    else if (token.startsWith("[")) {
      const close = token.indexOf("](");
      const href = token.slice(close + 2, -1);
      out.push(
        <a key={k} href={/^https?:\/\//.test(href) ? href : undefined} className="text-accent underline" target="_blank" rel="noreferrer">
          {token.slice(1, close)}
        </a>,
      );
    } else out.push(<em key={k}>{token.slice(1, -1)}</em>);
    last = at + token.length;
  }
  if (last < text.length) out.push(plain(text.slice(last), `${key}-tail`));
  return out;
}

const cells = (line: string) =>
  line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((one) => one.trim());

export function Markdown({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const lines = text.split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i] ?? "";
    const key = `b${String(i)}`;
    if (line.trim() === "") {
      i++;
      continue;
    }
    if (line.startsWith("```")) {
      const body: string[] = [];
      const language = line.slice(3).trim();
      i++;
      while (i < lines.length && !(lines[i] ?? "").startsWith("```")) body.push(lines[i++] ?? "");
      i++;
      blocks.push(<CodeBlock key={key} code={body.join("\n")} language={language === "" ? undefined : language} />);
      continue;
    }
    if (/^\s*\|/.test(line) && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] ?? "")) {
      const head = cells(line);
      i += 2;
      const rows: string[][] = [];
      while (i < lines.length && /^\s*\|/.test(lines[i] ?? "")) rows.push(cells(lines[i++] ?? ""));
      blocks.push(
        <div key={key} className="overflow-x-auto">
          <table className="w-full border-collapse text-[14px]">
            <thead>
              <tr>
                {head.map((one, c) => (
                  <th key={c} className="border-b border-rule px-2 py-1.5 text-left font-semibold">
                    {inline(one, `${key}h${String(c)}`, streaming)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, r) => (
                <tr key={r}>
                  {row.map((one, c) => (
                    <td key={c} className="border-b border-rule-2 px-2 py-1.5 align-top">
                      {inline(one, `${key}r${String(r)}c${String(c)}`, streaming)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    const heading = /^(#{1,4})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push(
        <p key={key} className="font-semibold">
          {inline(heading[2] ?? "", key, streaming)}
        </p>,
      );
      i++;
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i] ?? "")) items.push((lines[i++] ?? "").replace(/^\s*([-*]|\d+\.)\s+/, ""));
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={key} className={ordered ? "list-decimal space-y-1 pl-5" : "list-disc space-y-1 pl-5"}>
          {items.map((one, n) => (
            <li key={n}>{inline(one, `${key}-${String(n)}`, streaming)}</li>
          ))}
        </List>,
      );
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && (lines[i] ?? "").trim() !== "" && !/^\s*([-*]|\d+\.)\s+|^\s*\||^```|^#{1,4}\s/.test(lines[i] ?? "")) para.push(lines[i++] ?? "");
    blocks.push(<p key={key}>{inline(para.join(" "), key, streaming)}</p>);
  }
  return (
    <div className="space-y-2.5 break-words">
      {blocks}
      {streaming ? <StreamCaret /> : null}
    </div>
  );
}
