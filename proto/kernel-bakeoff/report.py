"""Summarize runs/**/log.json into RESULTS.md and apply the pre-registered decision rule."""
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent
LIBS = ["build123d", "cadquery"]
WIN_MARGIN = 0.10

logs = [json.loads(p.read_text()) for p in sorted(ROOT.glob("runs/*/*/*/*/log.json"))]
by = defaultdict(list)
for log in logs:
    by[log["lib"]].append(log)
    by[(log["lib"], log["model"])].append(log)
    by[(log["lib"], log["part"])].append(log)
models = sorted({log["model"] for log in logs})
parts = list(dict.fromkeys(log["part"] for log in logs))


def rate(group, key):
    return sum(g[key] for g in group) / len(group) if group else float("nan")


def pct(x):
    return f"{x * 100:.0f}%"


lines = ["# Kernel bake-off results", "",
         f"{len(logs)} cells: {len(parts)} parts x {len(LIBS)} libraries x {len(models)} models "
         f"({', '.join(models)}), one repair round after any failure. Zero-shot, no library docs.", "",
         "## Strict pass rate", "",
         "| Library | n | First try | After one repair |", "| --- | --- | --- | --- |"]
for lib in LIBS:
    g = by[lib]
    lines.append(f"| {lib} | {len(g)} | {pct(rate(g, 'first_try'))} | {pct(rate(g, 'after_repair'))} |")

lines += ["", "## By model", "", "| Library | Model | n | First try | After one repair |",
          "| --- | --- | --- | --- | --- |"]
for lib in LIBS:
    for m in models:
        g = by[(lib, m)]
        lines.append(f"| {lib} | {m} | {len(g)} | {pct(rate(g, 'first_try'))} | {pct(rate(g, 'after_repair'))} |")

lines += ["", "## By part (passes after repair / cells)", "", "| Part | " + " | ".join(LIBS) + " |",
          "| --- | " + " | ".join("---" for _ in LIBS) + " |"]
for part in parts:
    cells = [by[(lib, part)] for lib in LIBS]
    lines.append(f"| {part} | " + " | ".join(f"{sum(c['after_repair'] for c in g)}/{len(g)}" for g in cells) + " |")

lines += ["", "## Failure categories, every failed attempt", "",
          "| Library | " + " | ".join(["runtime_error", "timeout", "no_output", "invalid_solid", "bbox", "volume", "features"]) + " |",
          "| --- |" + " --- |" * 7]
for lib in LIBS:
    c = Counter(a["category"] for log in by[lib] for a in log["attempts"] if not a["pass"])
    lines.append(f"| {lib} | " + " | ".join(str(c[k]) for k in
                 ["runtime_error", "timeout", "no_output", "invalid_solid", "bbox", "volume", "features"]) + " |")

lines += ["", "## Cost per generation call (median)", "", "| Library | Seconds | Output tokens | USD |",
          "| --- | --- | --- | --- |"]
for lib in LIBS:
    atts = [a for log in by[lib] for a in log["attempts"]]
    med = lambda k: statistics.median(a[k] or 0 for a in atts)
    lines.append(f"| {lib} | {med('duration_ms') / 1000:.1f} | {med('output_tokens'):.0f} | {med('cost_usd'):.3f} |")

lines += ["", "## Representative failures", ""]
for lib in LIBS:
    fails = [(log, a) for log in by[lib] for a in log["attempts"] if not a["pass"]]
    seen = set()
    for log, a in fails:
        if a["category"] in seen or len(seen) >= 3:
            continue
        seen.add(a["category"])
        detail = a["detail"].strip().splitlines()[-1] if a["detail"].strip() else ""
        lines.append(f"- **{lib}**, {log['model']}, `{log['part']}` sample {log['sample']}: "
                     f"`{a['category']}`. {detail[:240]}")

b, c = rate(by["build123d"], "after_repair"), rate(by["cadquery"], "after_repair")
lines += ["", "## Decision", ""]
if (b > 0.9 and c > 0.9) or (b < 0.1 and c < 0.1):
    lines.append(f"No decision. Both libraries scored {pct(b)} and {pct(c)}, so these prompts do not "
                 "discriminate. Harder prompts are needed before this result means anything.")
elif abs(b - c) >= WIN_MARGIN:
    winner = "build123d" if b > c else "cadquery"
    lines.append(f"**{winner}** wins: {pct(b)} vs {pct(c)} after repair, a gap of at least "
                 f"{pct(WIN_MARGIN)}, the pre-registered margin.")
else:
    lines.append(f"Tie: {pct(b)} vs {pct(c)} after repair is inside the {pct(WIN_MARGIN)} margin. "
                 "Per the pre-registered rule, default to **build123d** and carry the question into the "
                 "50-prompt comparison.")

(ROOT / "RESULTS.md").write_text("\n".join(lines) + "\n")
print("\n".join(lines))
