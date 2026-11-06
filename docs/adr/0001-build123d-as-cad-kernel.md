# build123d is the code-CAD library

We build on build123d, not CadQuery. A bake-off on branch `proto/kernel-bakeoff` (commit `142404a`) had Sonnet and Opus generate 10 robot parts three times in each library, graded by a kernel-neutral checker: both libraries scored 97% first try and 100% after one repair, so model reliability did not separate them on single parts. The tie went to the surrounding ecosystem: the standard-part generators we plan to use (bd_warehouse, py_gearworks) and the joint objects assemblies need are native to build123d. CadQuery's larger presence in model training data did not show up as a measurable advantage.

## Consequences

The bake-off's prompts were too easy to discriminate. If edits to existing models or multi-part assemblies turn out to be much less reliable in build123d, that is the evidence that would reopen this decision.
