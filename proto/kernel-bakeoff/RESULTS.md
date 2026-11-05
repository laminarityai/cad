# Kernel bake-off results

120 cells: 10 parts x 2 libraries x 2 models (opus, sonnet), one repair round after any failure. Zero-shot, no library docs.

## Strict pass rate

| Library | n | First try | After one repair |
| --- | --- | --- | --- |
| build123d | 60 | 97% | 100% |
| cadquery | 60 | 97% | 100% |

## By model

| Library | Model | n | First try | After one repair |
| --- | --- | --- | --- | --- |
| build123d | opus | 30 | 97% | 100% |
| build123d | sonnet | 30 | 97% | 100% |
| cadquery | opus | 30 | 100% | 100% |
| cadquery | sonnet | 30 | 93% | 100% |

## By part (passes after repair / cells)

| Part | build123d | cadquery |
| --- | --- | --- |
| arm | 6/6 | 6/6 |
| bearing_block | 6/6 | 6/6 |
| gusset | 6/6 | 6/6 |
| hex_spacer | 6/6 | 6/6 |
| l_bracket | 6/6 | 6/6 |
| motor_plate | 6/6 | 6/6 |
| plate | 6/6 | 6/6 |
| shaft_collar | 6/6 | 6/6 |
| spur_gear | 6/6 | 6/6 |
| u_bracket | 6/6 | 6/6 |

## Failure categories, every failed attempt

| Library | runtime_error | timeout | no_output | invalid_solid | bbox | volume | features |
| --- | --- | --- | --- | --- | --- | --- | --- |
| build123d | 1 | 0 | 0 | 0 | 0 | 0 | 1 |
| cadquery | 2 | 0 | 0 | 0 | 0 | 0 | 0 |

## Cost per generation call (median)

| Library | Seconds | Output tokens | USD |
| --- | --- | --- | --- |
| build123d | 4.2 | 366 | 0.010 |
| cadquery | 3.8 | 336 | 0.010 |

## Representative failures

- **build123d**, opus, `u_bracket` sample 0: `features`. 0 cylinders at r=2.0, need 2
- **build123d**, sonnet, `u_bracket` sample 0: `runtime_error`. NameError: name 'Alignment' is not defined
- **cadquery**, sonnet, `u_bracket` sample 1: `runtime_error`. OCP.OCP.Standard.Standard_Failure: BRep_API: command not done

## Decision

No decision. Both libraries scored 100% and 100%, so these prompts do not discriminate. Harder prompts are needed before this result means anything.
