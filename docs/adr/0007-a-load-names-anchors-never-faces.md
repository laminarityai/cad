# A load names anchors, never faces

FEA needs to know where a part is held and where the load acts. The agent writes the geometry and is graded on it, so if the agent chose those faces it could put the load where it does least harm. This ADR records how phase 3 places loads. The operator approved it on 2026-11-07, and [the phase 3 design](../design/phase-3.md) §2.1 gives the full rules. The amendment of 2026-11-11 at the end, accepted that day, lets the agent describe a load case from fixed terms that the server turns into words.

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

## Amendment (2026-11-11): load cases the agent describes

Status: Accepted. The operator decided on 2026-11-11 that the `fea` check must work for general CAD cases, with the agent making grounded judgments for what it does not know, and said to modify this ADR. The operator also approved new rules behind the words for a flat end and the far end (option A of [fea load anchors](../design/fea-load-anchors.md)), and ruled out both adding words one at a time and picking faces for each revision. This amendment records how a load case reaches past the five reviewed phrases. The operator approved it on 2026-11-11 with three decisions. The terms are approved now, and agent-written code that picks the faces is deferred, not rejected. A described load case may be proposed after variants exist, until the brief has its first `fea` result. Supports that rest, slide or pivot stay unverified, as their own piece of work ([#254](https://github.com/laminarityai/cad/issues/254)). [Load cases the agent describes](../design/fea-described-loads.md) gives the options, the rules, the harness cases and the build order.

### The agent composes terms, and the server writes the words

A load case may use terms from a second closed list. The support terms find:

- the flat face at one end of the middle or short principal axis;
- one of two flat faces that face each other across a gap;
- each hole, or each inner curved face, of a diameter when one is given;
- the holes that open on one flat face.

The load terms find the largest flat face or its middle, the face across the gap from a facing support, and the hole or inner curved face farthest from the supports. Two directions are added. One presses into the loaded face, and one pulls straight away from the supports. A load case that uses any of these terms is a described load case.

The server writes the words the person confirms from the terms, with the same function that writes the reviewed phrases. The agent supplies no words for a load case, so the words say exactly what the check runs. The agent still never names a face, writes no code that finds one, and never chooses a frame.

Each term is fixed code in `fea` that reads only normals, principal axes, centroids, areas, hole axes and the faces that holes open on. Every term gives candidates, and the check keeps the worst. A term with no match, a count that does not match, and more candidates than the check's limit give `unknown`, and the reason names the term. Adding a matching face never removes a candidate. An inner curved support has the same keep-out as a bore.

A new term needs evidence and harness cases, as a new phrase did. A new pairing of terms does not.

### Written before any stress result, and never changed after one

`propose_requirements` refuses a described load case that no earlier proposal of the brief carried, once any variant of the brief has a stored `fea` result, whatever its verdict. Once such a result exists, it also refuses a proposal that leaves out a described load case, unless the person declined since. Before any such result exists, the agent may replace a description, because it has seen no result to choose between. The force may still change, because it is the person's number. This is the result rule.

So a load stated after the options are built ("will it hold 5 kg?", which is how deeper analysis usually starts) can use the terms. A description the person declines can be replaced, until the first `fea` result of the brief.

The cost is that the agent picks the terms knowing the shape, as it already does when it picks a reviewed phrase. It never picks them knowing a stress result of that brief. The person still confirms words the server wrote. The result rule is looser than the blind rule for agent-written checks (ADR-0011) on purpose. A rule of "before any variant" would send the common path back to the five reviewed phrases.

So no `fea` result of the brief exists when a described load case is written, and no later result can change it.

One question is not settled. It is whether a `fea` result that is `unknown` because a term found no match counts as a result. This amendment takes the strict reading, so any stored `fea` result counts. Build step 2 reports how often that leaves an honest description stuck.

### Labelled and counted apart

The confirmation page marks a described load case as the agent's description. A verdict on one carries `load_case: "described"` on the scorecard. The agent reports a pass on one as "passes on a load case I described". The tracer counts these verdicts apart from verdicts on reviewed phrases, outside its headline count. Auto counts a pass on a described load case toward its stop, and the stop report names it. This follows how researched values are treated (ADR-0009).

### What this replaces

Paragraph 2 said that brief words the vocabulary cannot express give an unchecked requirement. That now holds for words that neither the reviewed phrases nor the described terms can express. Consequences said that the vocabulary grows only from evidence (#49). That still holds for each term, but terms combine without new evidence.

Every support stays fixed, and every load stays a force. A part that rests, slides or pivots, a load given as a displacement, and contact with another part stay unverified. Supports that rest, slide or pivot are their own piece of work ([#254](https://github.com/laminarityai/cad/issues/254)).

### Considered options

- **Words added one at a time (option B of fea load anchors).** Rejected by the operator on 2026-11-11. Each brief that needs a new phrase waits for one.
- **The faces that a confirmed context part touches.** Rejected. The agent sets where the variant sits in the context part's frame, so it would set which faces are held.
- **Agent-written code that picks the faces, gated like an agent-written check.** Not chosen now. Code can single out any face, and the person cannot read it, so the words on the page would be the agent's account of the code. The operator decides after build step 1 reports what the terms cover, measured on the corpus and the novice briefs.
- **The person picks faces for each revision (#79).** Rejected by the operator. Auto revises without the person.
- **A server model call that writes the terms from the person's words alone.** Not chosen now. The result rule already allows a described load case on a brief that has variants, so this would add only a new description after the brief has a stress result. The cost is a second model in the path of every verdict on a load.
