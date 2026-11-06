# Decision rule for the kernel edit and assembly comparison

This rule is fixed before any variant is graded. PR9 applies it to its run, and nobody may change it after the run starts. It answers the question in the Consequences section of ADR-0001: are edits to existing models and multi-part assemblies much less reliable in build123d than in CadQuery?

## What is measured

- A **cell** is one library, one model, one brief and one sample. The run has 50 briefs (30 edit, 20 assembly), 2 models (Sonnet and Opus) and 3 samples, so each library has 300 cells: 180 edit cells and 120 assembly cells.
- Each cell gets one first attempt and, if that attempt fails, one repair round, as in the bake-off.
- A cell is a **strict pass** when `grade.py` returns `"pass": true` for the last attempt. That means every check passes: the solid count and validity, no interference between parts, the change the brief asked for, every untouched feature, and the overall shape.
- A cell that ends in an API error is not a result. Rerun it. The run is complete only when every cell has a graded attempt.
- The **strict pass rate** of a group is its strict passes divided by its cells.
- The **gap** is the CadQuery strict pass rate minus the build123d strict pass rate, in percentage points.

## The rule

Apply the steps in order and stop at the first one that matches.

1. **No decision.** If both libraries score 90% or more over their 300 cells, or both score 10% or less, the briefs do not separate the libraries. ADR-0001 stands, and the result says that harder or easier briefs are needed before it means anything.
2. **Reopen ADR-0001.** If the gap is 10 points or more over all 300 cells, or 15 points or more over the 180 edit cells, or 15 points or more over the 120 assembly cells, reopen ADR-0001. PR9 records this in the ADR and does not change the stack. The operator decides what happens next.
3. **ADR-0001 stands.** In every other case, including any result where build123d scores higher, ADR-0001 stands.

## Why these numbers

- With 300 cells per library and pass rates near 70%, one standard error of the gap is about 3.7 points, so a 10 point gap is between 2 and 3 standard errors. The three samples of one brief are not independent, so the real error is larger. The margin matches the bake-off's 10 point margin in `report.py` at `142404a`.
- The per-kind thresholds are wider because each kind has fewer cells, and because the rule checks three gaps, which raises the chance that one of them crosses by luck.
- The 90% and 10% bounds repeat the bake-off's no-decision clause, which fired at `142404a` when both libraries scored 100%.

## Reported but not decisive

PR9 also reports the first-try strict pass rate, the rate per model, and the **silent edit damage rate** per library. That rate is the share of edit cells whose `target` check passes and whose `untouched` check fails. SPEC.md names this failure in its Risks section. These numbers explain the result. They do not change the outcome of the rule.
