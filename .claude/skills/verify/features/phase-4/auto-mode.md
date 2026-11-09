# Auto mode (NOT YET BUILT)

The server holds an Auto run. The web backend calls `auto_start`, then `auto_revise` with each new revision of the code, until the server returns `Stopped`. A run stops when every checked requirement passes, when a call proposes requirements or a row waits on a confirmation, when the agent calls `auto_ask`, or when the account's usage cap refuses a build (`AccountLimit`). `bounds_conflicts` stops a run before any build and warns on the Plan mode confirmation page.

Design: `docs/design/phase-4.md` §1b, §2.5 (ADR-0010, approved 2026-11-08) and §2.7 (`AccountMeter`). Units 7 and 9 of §4. Unit 1 (revisions in a slot) comes first and changes [Build variant](../build-variant.md): `build_variant` takes a `slot`.

## The checks §4 gives units 7 and 9

- Unit 7, Auto core: table tests for all pass, pending not counting toward all pass, proposing requirements stopping the run, `auto_ask` stopping it with the agent's note, and a cap refusal stopping it with `AccountLimit`. A scripted driver that keeps calling after `Stopped` is refused with no container started. An agent measurement cannot change `step`.
- Unit 9, conflict exit eval: on "fits in a 20 mm cube, PLA, at least 50 g" the confirmation page warns of the conflict, and the run stops with `NeedsPerson(conflict)` and its `Bounds` before any build. On a stiffness-versus-mass brief the agent stops and reports within 6 revisions, with a note that names both requirements.

## Proof to write when it lands

- Scripted driver with `cad-call`: confirm a brief (browser as the person), `auto_start`, `auto_revise` with the plate code, then call `auto_revise` again after `Stopped` and show the refusal with no new container (`docker ps -a --filter label=cad.sandbox` before and after). Cost: docker + browser.
- The conflict warning is on the confirmation page, so `browser.py` reads it from the ARIA snapshot of that page. The 20 mm cube brief stops before any build: the variant store under `$CAD_HOME` stays empty.
- The stiffness-versus-mass eval is a live run through the brief-set driver ([Brief set](../brief-set.md)). Cost: live.

## Until then

Auto mode has no code. Today's modes are instruction text, proved by [Test mode](../test-mode.md).
