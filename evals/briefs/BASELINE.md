# Brief-set baseline

A full run of `evals/briefs/run.py` over the private brief set (22 briefs, 8 domains), recorded on 2026-11-13 at commit `38461b6`. It holds numbers and brief ids only. The set, the transcripts and the per-brief files stay outside the repo. Rerun the command and compare: a change that lowers traced, strict pass rate or coverage, or raises confirmation pages or minutes, shows here.

```
uv run python evals/briefs/run.py --briefs ~/cad-evals/briefs --out ~/cad-evals/runs/<stamp> --model sonnet --jobs 2
```

Sessions ran on `claude-sonnet-5-5` (`--model sonnet`), two at a time, with the scripted person confirming every page after one second. Two sessions failed the harness guard and were run again once with `--only` into the same `--out`. bracket-01 finished on the second try, and mechanism-02 failed again. Had the first tries stood, 20 of 22 would have finished and 19 traced, with 43/64 (67%) strict and 48/64 (75%) covered. The 2026-11-08 baseline reran its two failures of the same kind the same way. This is one run, so it gives no spread.

| Number | Baseline |
| --- | --- |
| Briefs finished | 21/22 (mechanism-02 failed both tries) |
| Briefs traced (`--require-judged`) | 19/22 |
| Numbers resolved, cards the session was shown | 4064/4071, over 124 cards |
| Numbers resolved, cards read after the session | 2292/2299, over 80 cards, all judged |
| Agent measurements counted as not verified | 0 |
| Strict pass rate (#49) | 47/69 requirements (68%) |
| Requirements covered by reviewed checks (#49) | 52/69 (75%) |
| The same two rates without the 2 untraced briefs | 43/61 (70%) and 47/61 (77%) |
| Decided by an approved agent-written check | 0/69 |
| Decided on a load case the agent described, counted apart | 1/69 |
| Confirmation pages per brief (#50) | 1 for each of the 21 finished briefs |
| Minutes from brief to first scorecard (#50) | median 0.6, range 0.4 to 1.0 over 21 briefs |
| Cost | 7.15 USD spent: 6.52 USD for the set and 0.63 USD for the two reruns. The result files sum to 6.29 USD because each rerun replaced its first try, and the 2026-11-08 figure of 2.35 USD is on that basis |
| Session time | median 84 s, longest 165 s |

## What limits coverage

Of the 69 requirements, 17 are not covered.

- 15 have the `unchecked` kind. The agent proposed them, and no check decides that kind. By keyword family they are sizes and shapes 5, holes and fasteners 3, walls and thickness 2, loads and stiffness 2, fits and clearances 1 and other 2.
- 1 is a deflection limit whose stress check was still running when the session ended (conflict-stiffness-mass). The runner reads the stores as soon as the session ends and does not wait for a background check, and no record of that job was stored. This is the harness's timing (issue #306). It understates coverage by at most 1, to 52/69 from 53/69.
- 1 is a safety factor decided on a load case the agent described. It passed, and it is counted apart, not as covered (bracket-01).

Three covered requirements read unknown, so they count as covered and not as passing. Two are mass limits on a material with no row in the table, where the agent did not research the density (bracket-02, robot-03). One is a hole requirement on a part whose openings are not all round holes, so the holes check could not measure them all (enclosure-03).

## Why this differs from the 2026-11-08 baseline

The 2026-11-08 baseline was 20/20 traced after two sessions were rerun, a strict pass rate of 53/103 (51%) and coverage of 56/103 (54%), for 2.35 USD at four sessions at a time. The two runs do not compare directly, for three reasons.

- The requirements differ. On 2026-11-08 the agent proposed 47 requirements of the `unchecked` kind out of 103 (46%). Here it proposed 15 out of 69 (22%). In both runs checks covered nearly every requirement of a kind they decide: 56 of 56 then, 52 of 54 now. So the rise from 54% to 75% is the fall in `unchecked` requirements, not checks covering more of the same requirements. Part of the fall is new checks. 4 fastener-hole and 4 plain-hole requirements have kinds no check decided on 2026-11-08, and counted as `unchecked` they would put coverage at 44/69 (64%). The rest is the agent proposing fewer requirements no check decides. That is the agent's choice, not a gain in the product.
- The set grew from 20 to 22 briefs, with two conflict briefs. On the 20 briefs both runs share, 19 finished here, with 46/64 (72%) strict and 49/64 (77%) covered. The set's own count is 77 requirements over the 22 briefs, and it labels 41 of them `unchecked`. Its labels predate the hole kinds.
- The basis changed. The 2026-11-08 rates came from the last scorecard of each session. These come from the server's reading after each session, of the last variant scored (issue #301 holds the open question about that basis).

## How to read untraced briefs

- bracket-01 and conflict-stiffness-mass are untraced only because of the stress check's `where` faces. That is the face indices under `results[i].where.support` and `results[i].where.load`, and the reason reads "no rule places a number at results[6].where...". The tracer already requires the shown `where` to equal the signed job result's, and in both briefs the faces on the card are the faces in the signed record. The tracer walk has no rule that places those integers, so it counts them as unresolved (issue #306). They are the 7 unresolved numbers on the shown cards and the 7 on the readings, and there are no others.
- A brief whose reason contains "unknown, but its signed job result holds" is an honest retry after a refused job, not a dishonest session (issue #303). No brief in this run had that reason.
- mechanism-02, the first try of bracket-01, and two sessions in the first 2026-11-08 run all failed the same way. The model called `build_variant` without the `mcp__cad__` prefix, the harness refused the call, and `claude_session.py` failed the session on a tool outside cad (issue #306).
- The tracer and harness now close these gaps, so a run after this baseline reads differently. Face indices are bound to the signed result's `where`, a call refused as no such tool is counted as model friction instead of failing the session, a check job with no stored result after the session (cut off, refused and not retried, or timed out) is named apart, a rerun keeps the earlier try under `try-<n>`, and an honest retry after a refused job traces. Re-traced with that tracer, this run's stored homes trace 21 of 21 finished briefs, and mechanism-02's session passes and traces. The numbers above are unchanged.

## Reading the numbers

- The requirements counted are the ones the agent proposed and the scripted person confirmed. The scripted person never declines, so a requirement the agent dropped or changed is in neither rate. A `made_of` requirement names the material and is not judged, so neither rate counts it.
- In build-first the agent scores before the person confirms, and Confirm judges the same stored results with no rebuild. So after each session the tracer reads every variant scored with a brief through the server's own `scorecard` operation, and the rates come from that reading of the last variant scored. A run counts the cards the session was shown apart from the readings after it. The shown count holds every card a tool returned, so a variant scored twice counts twice. The readings hold one card for each variant, material and brief a shown card was scored with.
- The pooled rates include the briefs that did not trace (issue #301). The row without them is there so a reader can see the difference.
- Minutes leave out the person's reading time, which is one second here.
