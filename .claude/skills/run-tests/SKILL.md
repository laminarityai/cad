---
name: run-tests
description: Which checks to run on this laptop, which to leave to CI, and how to wait for CI without stalling. Use before you run `uv run verify`, pytest or a live walk, when a brief says verify must be green, and whenever a check run would take more than a minute.
---

# Run tests

The full suite takes about 10 minutes on this laptop and about 3 minutes in CI, which runs it on 8 shards for every PR. CI is the gate. Run only fast checks here.

## While you work

Run the tests for the directory you changed, on four workers:

```
uv run pytest -q -x -n 4 --dist loadfile tests/<feature>
```

Most directories take seconds. The ones that start sandbox containers take minutes. `tests/shard_seconds.json` records over 80 s each for `tests/checks` (about 290 s), `tests/variant_sets`, `tests/briefs`, `tests/agent_measurements`, `tests/sandbox`, `tests/fea` and `tests/scorecard`. In those, run the one file you changed.

Run the web tests when you change `web/`:

```
uv run verify --only "web test"
```

## Before you push

Run the fast steps. They run side by side and take about 15 seconds. The pre-commit hooks run the type checks, lint, format, file size and materials table steps on every commit. They run `api types`, the web steps and `protocol models` only when the commit changes the files `.pre-commit-config.yaml` names for each. The other slow steps run only in CI:

```
uv run verify
```

Do not run `uv run verify --all` or a bare `uv run pytest`. They run the slow steps (the full test suite, the sandbox image, protocol models and the app step), and CI runs those faster. Run one slow step only to debug a CI failure in it, with `--only`, for example `uv run verify --only "protocol models"`.

## Push and wait for CI

Push the branch and open the PR as soon as the fast steps pass. Do not wait for local proof first. Then block on CI in one call:

```
gh pr checks <number> --watch --fail-fast
```

Give the Bash call a 600000 ms timeout and run it in the background. You are notified when it exits. Do not poll in a loop, and do not sleep. While CI runs, do the live walk or write the PR description.

When a check fails, read its log with `gh run view <run-id> --log-failed`, fix it, push, and watch again.

## Live proof

Do one live walk per PR, at the end, after the code is final. A live walk costs minutes and model money. Prove a fix made after the walk with the cheapest path in the [verify skill](../verify/SKILL.md) cost table, not with a second full walk.

## Never wait on another agent's PR

If your change needs code from an open PR, fold that code into your branch, or stop and report the dependency. Do not watch another PR's CI.

## When Docker or the disk fails

A check that starts a container hangs when Docker is down or the disk is full. Check with `docker info` and `df -h /System/Volumes/Data`. Do not retry the same run. Push and let CI run the container steps, and report the problem.
