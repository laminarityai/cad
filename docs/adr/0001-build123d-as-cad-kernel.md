# build123d is the code-CAD library

We build on build123d, not CadQuery. A bake-off on branch `proto/kernel-bakeoff` (commit `142404a`) had Sonnet and Opus generate 10 robot parts three times in each library, graded by a kernel-neutral checker: both libraries scored 97% first try and 100% after one repair, so model reliability did not separate them on single parts. The tie went to the surrounding ecosystem: the standard-part generators we plan to use (bd_warehouse, py_gearworks) and the joint objects assemblies need are native to build123d. CadQuery's larger presence in model training data did not show up as a measurable advantage.

## Consequences

The bake-off's prompts were too easy to discriminate, and it covered single parts only. On 2026-11-06 we dropped the planned 50-brief comparison of edits and assemblies, because we will not use CadQuery. A weakness in build123d on edits or assemblies is now ours to work around, not evidence that reopens this decision.
