# Brief-set baseline

The first full run of `evals/briefs/run.py` over the private brief set (20 briefs, 7 domains), recorded on 2026-11-08. It holds numbers and brief ids only. The set, the transcripts and the per-brief files stay outside the repo. Rerun the command and compare: a change that lowers traced, strict pass rate or coverage, or raises confirmation pages or minutes, shows here.

```
uv run python evals/briefs/run.py --briefs ~/cad-evals/briefs --out ~/cad-evals/runs/<stamp> --jobs 4
```

Sessions ran on `claude-sonnet-5-5` (`--model sonnet`), four at a time, with the scripted person confirming every page after one second.

| Number | Baseline |
| --- | --- |
| Briefs traced (`--require-judged`) | 20/20, over 37 final scorecards and 859 numbers, all resolved |
| Agent measurements counted as not verified | 0 |
| Strict pass rate (#49) | 53/103 requirements (51%) |
| Requirements covered by reviewed checks (#49) | 56/103 (54%) |
| Confirmation pages per brief (#50) | 1 for each of the 20 briefs |
| Minutes from brief to first scorecard (#50) | median 0.5, range 0.4 to 0.8 over 19 briefs (robot-03 not measured: its file times span more than its session ran, so the machine slept) |
| Cost | 2.35 USD for 20 briefs, 0.12 USD each |
| Session time | median 50 s, longest 68 s |

## Reading the numbers

- The requirements counted are the ones the agent proposed and the scripted person confirmed, on the last scorecard of each session. The scripted person never declines, so a requirement the agent dropped or changed is in neither rate. The set's own count is 72 requirements, of which 32 have a kind a check decides today (44%). The two do not compare directly: the agent's proposals have 103 requirements, with kinds the set's count does not list.
- In build-first the agent scores before the person confirms, and Confirm judges the same stored results with no rebuild. So after each session the tracer reads every variant scored with a brief through the server's own `scorecard` operation, and the rates come from that reading of the last variant scored. A card scored before Confirm counts as awaiting only until a later card or reading judges its variant. A run counts the cards the session was shown, and the numbers on them, apart from the readings after it. The shown count holds every card a tool returned, so a variant scored twice counts twice. The readings hold one card per variant scored with a brief. The 37 cards and 859 numbers above are the one card the server stored for each variant, traced from the store after the session, so a new run's readings are the count closest to them. The 2026-11-08 rates come from the last scorecard of each session, which in that flow was already judged.
- Minutes leave out the person's reading time, which is one second here.
- A first run of the same code had 18/20 traced and 2 sessions failed (jig-02 and robot-03). The model called `build_variant` and `list_requirements` without the `mcp__cad__` prefix, the harness refused each call, and `claude_session.py` failed the session on a tool outside cad. A rerun of those two with the same `--out` traced both. It hit 2 of 20 sessions.
