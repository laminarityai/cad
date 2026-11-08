# Test mode

Test mode is deeper analysis of one variant the user picks. It has no server state, no mode argument and no second fidelity. It is guidance: the server's `instructions` end with a Test mode paragraph, and the `score_variant` description says to score only the picked variant. The proof is a real Claude Code session that follows it on the hook brief of `docs/design/phase-3.md` §1a.

## Sub-features

- `test-mode-text` sends the Test mode paragraph as the last part of the server's `instructions`. `tests/server/test_scorecard_tools.py` asserts it.
- `test-mode-hook` makes Claude Code, in a second session on the same server home, score only the variant the user picked, with its `brief_id`, and report the load and print time as not checked, with no estimate of its own.
- `test-mode-new-load` has the user state a load no confirmed requirement holds. Claude Code proposes it, the scripted person confirms it, and only then does Claude Code score the picked variant.

## How to get to it (user POV)

After the scorecards of a Design mode run, the user names one variant and asks whether it will hold a load or how long it takes to print.

## Driving it with claude_session.py

Preconditions are those of [Briefs](./briefs.md) and [Score variant](./score-variant.md). All three sessions share one server home, so set it once:

```
export CAD_TEST_HOME="$EVIDENCE/home"
```

- **Design run.** Run `CAD_HUMAN_LOG="$EVIDENCE/human-design.jsonl" uv run python .claude/skills/verify/scripts/claude_session.py --home "$CAD_TEST_HOME" --opener "$PWD/.claude/skills/verify/scripts/human.py" "A wall hook for a 5 kg bag. It screws to the wall through two M5 holes. Printed in Bambu PLA Basic on my P1S. Under 2 hours to print. Please design it: get my requirements confirmed, then build three variants and score each one." "$EVIDENCE/claude-hook-design.json"`. The calls run `create_brief`, `propose_requirements`, `ask_to_confirm`, then `build_variant` and `score_variant` for each variant. Note the `brief_id`, the `project_id` and one scored `variant_id`.
- **Hook.** Run the same command with `CAD_HUMAN_LOG="$EVIDENCE/human-test.jsonl"`, the transcript `$EVIDENCE/claude-hook-test.json`, and the prompt `My wall hook brief is <brief_id> in project <project_id>. I pick variant <variant_id>. Test it: will it hold my 5 kg bag, and will it print in under 2 hours on my P1S?`. Every `score_variant` call names `<variant_id>` and `<brief_id>`. The reply says the load and the print time were not checked, and it gives no safety factor, stress, deflection or print time.
- **New load.** Run it again with `human-test-new-load.jsonl`, `claude-hook-test-new-load.json`, and the prompt `My wall hook brief is <brief_id> in project <project_id>. I pick variant <variant_id>. Test it: my kid may also hang a 12 kg backpack on it, so it has to hold 12 kg too.`. The calls run `create_brief` with that project and the user's words, `propose_requirements` with an `unchecked` 12 kg requirement, `ask_to_confirm`, then `score_variant` on `<variant_id>` only. The reply says the 12 kg load was not checked.

## Gotchas

- Today no check measures strength or print time, so a load or a print time is an `unchecked` requirement and the reply must call it not checked. Once a check decides one, the same drive should show that check's verdict instead.
- The 12 kg words are not in the first brief, and a quote must come from its brief, so the agent stores them as a new brief in the same project.
