# Deeper analysis

Deeper analysis is slower analysis of one variant the user picks. It is not a mode: it has no server state, no mode argument and no second fidelity. It is guidance: the server's `instructions` include a deeper analysis paragraph, and the `score_variant` description says to score only the picked variant. The proof is a real Claude Code session that follows it on the hook brief of `docs/design/phase-3.md` §1a.

## Sub-features

- `deeper-analysis-text` sends the deeper analysis paragraph as part of the server's `instructions`. `tests/server/test_scorecard_tools.py` asserts it.
- `deeper-analysis-hook` makes Claude Code, in a second session on the same server home, score only the variant the user picked, with its `brief_id`, and report the load and print time as not checked, with no estimate of its own.
- `deeper-analysis-new-load` has the user state a load no confirmed requirement holds. Claude Code proposes it, the scripted person confirms it, and only then does Claude Code score the picked variant.

## How to get to it (user POV)

After the scorecards of a Design mode run, the user names one variant and asks whether it will hold a load or how long it takes to print.

## Driving it with claude_session.py

Preconditions are those of [Briefs](./briefs.md) and [Score variant](./score-variant.md), with `browser.py start` done. All three sessions share `$CAD_HOME` and the one browser.

- **Design run.** Run `uv run python .claude/skills/verify/scripts/claude_session.py --opener "$CAD_BROWSER/bin/open" "A wall hook for a 5 kg bag. It screws to the wall through two M5 holes. Printed in Bambu PLA Basic on my P1S. Under 2 hours to print. Please design it: get my requirements confirmed, then build three variants and score each one." "$EVIDENCE/claude-hook-design.json"`. The calls run `create_brief`, `propose_requirements`, `ask_to_confirm`, then `build_variant` and `score_variant` for each variant. Note the `brief_id`, the `project_id` and one scored `variant_id`.
- **Hook.** Run the same command with the transcript `$EVIDENCE/claude-hook-test.json`, and the prompt `My wall hook brief is <brief_id> in project <project_id>. I pick variant <variant_id>. Test it: will it hold my 5 kg bag, and will it print in under 2 hours on my P1S?`. Every `score_variant` call names `<variant_id>` and `<brief_id>`. The reply gives the `fea` verdict for the load, says the print time was not checked, and gives no safety factor, stress, deflection or print time that `fea` did not return.
- **New load.** Run it again with the transcript `$EVIDENCE/claude-hook-test-new-load.json` and the prompt `My wall hook brief is <brief_id> in project <project_id>. I pick variant <variant_id>. Test it: my kid may also hang a 12 kg backpack on it, so it has to hold 12 kg too.`. The calls run `create_brief` with that project and the user's words, `propose_requirements` with a `min_safety_factor` 12 kg requirement, `ask_to_confirm`, then `score_variant` on `<variant_id>` only, again until nothing is pending. The reply gives the `fea` verdict for the 12 kg load.

## Gotchas

- The `fea` check decides a load, so the agent proposes it as `min_safety_factor` or `max_deflection`, not `unchecked`. The first `score_variant` call usually returns with `fea` pending and the load requirement `waiting`. The agent calls `score_variant` again with the same arguments until nothing is pending, then reports the `fea` verdict and its measures. When the material has no elastic modulus or Poisson's ratio, `fea` is `unknown` and the reply must say the load was not checked. No check measures print time yet, so a print time is still `unchecked`.
- The 12 kg words are not in the first brief, and a quote must come from its brief, so the agent stores them as a new brief in the same project.
