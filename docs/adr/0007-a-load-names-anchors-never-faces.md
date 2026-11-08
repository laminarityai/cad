# A load names anchors, never faces

FEA needs to know where a part is held and where the load acts. The agent writes the geometry and is graded on it, so if the agent chose those faces it could put the load where it does least harm. This ADR records how phase 3 places loads. The operator approved it on 2026-11-07, and [the phase 3 design](../design/phase-3.md) §2.1 gives the full rules.

A load case names anchors from a closed vocabulary, such as "the bores of exactly 2 holes of 5.5 mm" or "the end farthest from the supports". The load case is part of a requirement, and a person confirms it on the confirmation page (ADR-0004) with the rest of the set. The agent never names a face. Brief words that the vocabulary cannot express give an unchecked requirement, which the card shows as unverified.

Fixed code in the `fea` check resolves each anchor to a mesh region. The rules read only the geometry, never the model's coordinate frame. So a hole is a set of concave cylindrical faces around one axis line, and the far end is measured from the supports, not along a model axis. Turning or moving the model changes nothing.

Freedom that the words leave goes to the worst case. An unstated direction is a subspace, and the check solves one unit load for each basis vector and takes the exact worst direction from them. If two faces tie for one anchor, the check solves each and keeps the worse result.

A count that does not match fails closed. If the brief says 2 holes of 5.5 mm and the check finds 3, the requirement is `unknown`, and the reason names both counts. Adding a hole can never turn a fail into a pass.

A rigid bore makes the peak stress at its edge unbounded, so that peak depends on the mesh. The check therefore judges stress outside a fixed keep-out of 0.5 × bore diameter around each support hole. It reports the peak inside the keep-out as `support_max_von_mises` and does not judge it. The keep-out is a constant in the check, and the agent cannot change it.

## Considered options

- **The agent tags faces in its build code.** Rejected. The party that is graded would choose where the load goes.
- **Anchors resolved against the world axes or the bounding box.** Rejected. The agent picks the frame, so it could place a small flat at +x near the supports, and the words on the page would still read correctly to the person.
- **The person picks faces in a viewer for each variant (#79).** Not chosen for phase 3. It costs one confirmation per variant per load case, and phase 4 owns the viewer.

## Consequences

The worst case is conservative. A shelf bracket loaded "down" can fail on sideways bending that it would never see. In return, the agent cannot pass by turning the model, and the person never picks a face.

A brief whose loads the vocabulary cannot express stays unverified rather than approximated. The vocabulary grows only from evidence (#49).

A thin neck right at a bolt hole is not judged, because it lies inside the keep-out. The card's formula text states this gap. A later bolt-bearing check will cover it.

A region that a person picks in the viewer (#79) may later become a new anchor kind. A person would confirm it like any other anchor, so the agent still never names a face.
