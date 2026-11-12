# fea load anchors on the parts Auto builds

Issue #176 found that `fea` never decided on the parts Auto built for a cantilever brief. Two of its four reasons were anchors: "the part has no unique long axis" and "neither end of the long axis is a flat face". The other two, the node cap and the pending check, are fixed in the same change as this note. This note says which parts fail on anchors and why, gives three ways to fix it, and recommends one. It changes no code and no ADR.

## What fails

The evidence is a corpus of 19 parts that a person might ask a load question about, built for #176. It holds bars, L and T brackets, a hook, a truss arm, an I-beam arm, plates, and four parts from `tests/sandbox/parts`. Each part has the load case an agent would propose for "will it hold 20 N at the end?", in PLA, and is scored through `score_variant`. The issue's own Auto runs were not kept, so the corpus stands in for them.

11 of the 19 parts stop before any mesh, because an anchor does not resolve. The angles below were measured in the analysis image with the check's own `anchors` module.

| Part | Anchor | Reason the check gives | Measured cause |
|---|---|---|---|
| `l_plain` | `flat_end` | neither end of the long axis is a flat face | The principal long axis is 15.1° from the wall face's normal. The rule allows 0.057° (`END_ANGLE_TOL_RAD`). |
| `t_arm_flat_end` | `flat_end` | the same | The mounting plate sits off the T's centroid, so the long axis is 9.9° from both end faces. |
| `equal_angle` | `flat_end` | the same | The legs are equal, so the long axis is the diagonal, 45° from each leg's end. |
| `sb_gusset` | `flat_end` | the same | A triangle: no flat face lies at either extreme of its long axis. |
| `l_holes`, `l_gusset`, `t_arm`, `shelf_web` | `far_end` from 2 holes | no mesh triangle lies wholly on the anchored surface | The far end is measured along the line from the support to the centre of mass. That line is 4° to 19° off the long axis and 29° to 37° off the arm. The far band is only 0.5% of the reach deep (`FAR_FRACTION`), so on a tip face crossed at that angle it holds no whole mesh triangle. |
| `square_tab` | `flat_end` | the part has no unique long axis | A square: its two largest spreads are equal. |
| `sb_arm` | 1 hole of 28 mm | the brief names 1, the part has 2 | The load hole has the support hole's diameter. |
| `sb_l_bracket` | 2 holes of 5.1 mm | the brief names 2, the part has 4 | Each leg has 2 holes. |

The parts that resolve are bars whose long axis is normal to their end faces, such as a plain bar or a flat-ended I-beam, and parts that use `largest_flat` or `on_holes`. A cantilever arm with a mounting plate, or an L bracket, is what a person most often asks about, and it is what fails. The 1e-3 rad tolerance and the support-to-centre line suit a bar but not an asymmetric part.

## Option A: choose ends from whole flat faces, with the same words

Keep every anchor word and change the rules behind `flat_end` and `far_end`.

- **`flat_end`.** An end is a flat face that bounds the part (no material lies beyond its plane) and whose outward normal is within 30° of the long axis. At each end of the long axis, the end is the qualifying face whose centroid lies farthest along the axis. A face within `FLUSH_TOL_FRACTION` of it is part of the same end. When the two largest spreads tie, each tied axis gives candidates, and the check keeps the worst result, as it does for any tie.
- **`far_end`.** The load goes on the whole flat face farthest from the support. That face bounds the part, its outward normal is within 45° of the line from the support to the centre of mass, and its centroid reaches farthest along that line. When no flat face qualifies, as on a rounded tip, today's band rule applies.

How it fits ADR-0007: the words the person confirms do not change, so the page, the proposal guidance and the requirement models do not change. The rules read only normals, planes, principal axes and centroids, never the model's frame, so turning the model still changes nothing. Ties still go to the worst case, and a count that does not match still fails closed. The [phase 3 design](phase-3.md) §2.1 rule text, the check's formula text and the `fea` check version change. No ADR changes.

What it fixes, from the measured angles: `l_plain` (15°), `t_arm_flat_end` (10°), the four `far_end` parts, and `square_tab` through the tie rule. It leaves `equal_angle` (45°, a true tie between legs, outside a 30° cone), `sb_gusset` (no flat end), and the two hole counts.

The risk is that a 30° cone takes a chamfer or a sloped face as the end. A face must bound the part and be the farthest along the axis, which rules out a chamfer behind a flat end. The harness has to show this.

Harness cases A needs:

1. `tests/checks/test_anchors.py`, with fake faces: an L picks its wall face and its arm tip at a 15° tilt; a face 40° off the axis is not an end; a chamfer next to a flat end is not chosen; the far end of a bolted L is its whole tip face.
2. `tests/checks/test_anchors_in_image.py`: the same L and the T arm with its plate resolve to the same faces under the existing set of rotations and moves.
3. `tests/fea/cases.py`: a cantilever with a thick, off-centre mounting plate, fixed on the plate's back face and loaded at the arm tip. The expected value is the arm's Timoshenko tip deflection. Its bound has to be measured first, as §2.9 did for the existing bounds, because the plate adds some root compliance.

## Option B: new words in the closed vocabulary

Add anchor kinds for what the current words cannot say:

- holes qualified by where they are, such as "the 2 holes in one flat face" (`sb_l_bracket`: each leg's pair is a candidate, and the worse result is kept) or "the hole at one end" (`sb_arm`);
- a press on the middle of a named face (#209);
- end words that do not need a long axis, such as "the face opposite the support".

How it fits ADR-0007: the ADR expects the vocabulary to grow from evidence (#49). Each new kind is proposed with the brief's words and confirmed on the page like any anchor, its rule is geometry-only and frame-free, and ties go to the worst case. That is an addition to §2.1 and to the requirement models, not an amendment. The cost is more words for the agent to choose among and for a novice to read correctly on the page, plus page text and guidance for each kind.

Harness cases B needs, for each new kind: a hand-calc case and a tie case. For example, an L bracket with 2 holes in each leg, loaded at a tip, keeps the worse pair, and a bar with equal holes at both ends keeps the worse end.

## Option C: the person picks the faces in the 3D view

Selections (`sel-` records, #79) already let the person point at faces of one revision. A load case could name "the faces in this selection" as its support or its load.

How it fits ADR-0007: the agent still never names a face. But ADR-0007 did not choose this for phase 3 because of its cost, and `src/cad/selections/model.py` says that a selection is never a load or a check input. Both need amending. A selection belongs to one revision's geometry, so every option and every revision needs a new pick for each load case. Auto builds 3 to 5 options and revises them, so it would wait on the person at each step and could not run alone. The person would also have to choose geometry, which the operator wants the agent to own.

Harness cases C needs: few new numeric cases, because the region is given. It needs tests that a pick made on one revision cannot load another, and that a pick whose faces no longer exist fails closed.

## Recommendation

Do option A first. It fixes the cantilever arms with plates and the L brackets that people ask about most, and the person confirms the same words with no extra step. Add option B one kind at a time, starting with hole ties and the face press of #209, when the corpus or a walk shows the need. Keep option C out of load cases unless a brief appears that no geometry rule can express.

## Not an anchor: the large-displacement gate

4 corpus parts resolve and mesh, then stop at the 5% gate for linear analysis: `cantilever_bar` (5.6 mm on 100 mm), `l_filleted` (11.0 mm), `hook` (3.6 mm on 59 mm) and `truss_arm` (13.3 mm). Each is far over any deflection limit a person would set, yet the requirement is unknown. A geometrically nonlinear solve (`NLGEOM`) would decide them, but it breaks the superposition of unit solves that the worst-direction search relies on. This needs its own issue.

## Not an anchor: the node-cap floor on thin, filleted walls

With the floor at half each mesh's size, `i_beam_arm` (a 100 mm I-beam with 1 mm fillets at the web, on a wall plate) now passes, but `i_beam_flat` (the same beam with flat ends, sizes 1.79 and 1.20 mm) is still over the cap: its fine mesh has 157,432 nodes. The fillets set that count. With no element under the fine size it has 55,502 nodes, the same as with no curvature refinement. Three ways to fit it were measured in the check image (gmsh 4.8.0), and each has a cost:

| Change | Fine mesh nodes | Cost |
|---|---|---|
| Floor at 0.75 of each size | 87,152 | The coarse mesh has 2 tetrahedra with a negative Jacobian at a Gauss point (elements 1.34 mm wide on a 1 mm fillet, with midside nodes on the curve), and CalculiX stops with "nonpositive jacobian". |
| Floor at 0.75, midside nodes on straight edges (`Mesh.SecondOrderLinear`) | 87,152 | No inverted element, but a midside node on a 4.5 mm bore then sits h²/8r, about 0.12 mm, off the surface (worked out, not measured), while `region_faces` takes a triangle only when all 6 nodes are within 1e-4 of the extent (0.01 mm). So hole supports would match no faces. |
| One floor for both meshes, half the coarse size | 87,152 | No inverted element. Near the fillets, though, both meshes have the same size, so the 3% gate no longer tests refinement there. |

The third is the smallest change that fits. It weakens what the gate proves near fillets, so it is a decision for the operator, not a tuning.
