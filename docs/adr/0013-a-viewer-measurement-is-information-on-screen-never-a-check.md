# A viewer measurement is information on the screen and never a check

Status: Proposed, 2026-11-12. The operator has picked one part: a viewer measurement never reaches the scorecard or a verdict. The operator has not yet approved the rest of its text.

The viewer tools feature turns on measuring, sectioning and exploding in the 3D viewer, and draws the `extents` check's numbers as dimensions on the part. AGENTS.md says that checks decide and the agent never does. The server's guidance tells the agent to state a dimension only when a `score_variant` result returned it, and to name the check. A measure tool breaks the pattern. It computes a number in the person's browser from the drawn geometry, and no check computed that number. This ADR names that number, says where it may go, and says how the `extents` dimensions differ from it.

The evidence comes from a prototype run on 2026-11-12. The run flipped the library flags locally and drove the workspace in headless Chromium against an L bracket with two 5.5 mm holes and a 6 mm fillet. The design note [viewer-tools.md](../design/viewer-tools.md) has the numbers and the screenshots. Three findings shaped the decision:

- The library's mesh numbers are close to the kernel's. They are exact for planes and straight edges. A circle edge's length came out 0.16% to 0.41% short. The library gives no radius for a cylinder face.
- The library's hover line showed numbers such as "plane: area ≈ 1692.50" under the part, with nothing to say that no check measured them ([screenshot](../review/viewer-tools-library-distance.png)). The line does not depend on the measure flag. The app on `main` already draws it, half hidden behind the pick hint ([screenshot from the selection PR](../review/select-1-face.png)).
- A selection sends face and edge indices only. The server resolves them against the stored topology, signs a selection record, and the agent reads exact kernel numbers for it with `read_selection`. No number travels from the browser.

## The decision

### The number is called a viewer measurement

A viewer measurement is a number that the web app shows for the faces and edges the person has selected. The web app works it out in the browser from the geometry it already holds. There are two sources:

- **One face or edge.** The readout shows the topology facts the server sent with the mesh: area, length, radius, centre and normal. They come from the kernel and are the same numbers `read_selection` gives the agent.
- **Two faces or edges.** The browser computes the distance and the angle between them. Two parallel planes get the gap between their planes, from the topology. Any other pair gets the distance between closest points, from the mesh.

GLOSSARY.md gains the term when the operator accepts this ADR.

### The screen says it is not a check

The person sees one readout, next to the selection hint on the canvas. Its last line is always "Measured on screen. Not a check." A number taken from the mesh where either pick is curved starts with "≈". The readout uses no pass or fail colour and no verdict icon. The library's hover line, toolbar and measure panels stay off.

The cost: one more line of text on the canvas each time the person selects something.

### It never leaves the browser as data

The selection still sends indices only. No route, tool input, selection record or chat message carries a viewer measurement as a field. The agent gets its own exact numbers for the same selection from `read_selection`, as it does today. They are information under ADR-0008.

The person may type a number they read off the screen into the chat. That is the person's words. A stated number follows the path it follows today: the agent proposes it as a requirement that quotes those words, and the person confirms it.

The cost: the agent cannot see the number the person is looking at. If the readout says 65.28 mm and the person writes "make this 70", the agent learns 70 from the words and the faces from the selection. To learn the 65.28 mm, it reads the selection itself.

### It never grades

A viewer measurement never appears on the scorecard, in a verdict, or among the reasons Auto stops. No check reads it, and no check reads anything the browser computed. This is the operator's pick.

The cost: a person who wants a gap held to a number must say the number, and a check must measure it. No check measures the distance between two faces a person picked, so some gaps a person can measure on screen cannot be checked yet.

### The extents dimensions are the check's numbers

The viewer draws three dimension lines, along x, y and z, for the variant on screen. Each line's number is `extent:x`, `extent:y` or `extent:z` from that variant's `extents` result. The lines carry the label "Size check", which matches the row the Checks card already shows as "Size". These are a check's numbers, and the viewer shows them as such.

The viewer draws them only when the `extents` result for the variant on screen has passed. A result that is pending, unknown or failed draws no lines, and the viewer never falls back to a number of its own. `extents` needs `closed_solid` to pass, so an open shell gets no dimensions.

The `extents` result holds sizes, not corner positions. The viewer places the lines on the corners of the mesh bounding box and never shows that box's numbers.

The cost: the mesh box and the check's box come from different code. On the bracket they agreed exactly, at 60 × 40 × 70 mm. On a curved part they may differ by up to the mesh deflection. The line would then be a little longer or shorter on screen than its label says. The label is always the check's number.

## Consequences

- **ADR-0007** holds. The graded party never chooses where a measurement happens. A selection is still where a change goes, never a load or a check input.
- **ADR-0008** holds where ADR-0011 kept it. A measurement no person approved is information, never a verdict. A viewer measurement is the person's own tool, so it is information too.
- **ADR-0011** holds. A check the agent writes and the person approves may one day measure a gap the person points at. It would read the geometry with its own code, never the browser's number.
- The guidance in `src/cad/operations/guidance.py` does not change. The agent still states only the numbers a check returned.
- The readout and the agent can show different numbers for one selection. For two picks, the agent has no number at all. The design note keeps the readout's wording close to what `read_selection` returns, so the two read alike.
- The library's own measure tools stay off. The readout reads the library's mesh backend directly. The app hides the library's hover line, which shows unlabelled numbers on `main` today.

## Considered options

- **Turn on the library's measure tools as shipped.** Rejected. In the prototype, the library's clicks went to the workspace pick handler: a click replaced the selection, and the distance panel stayed empty. The toolbar covered the Download button ([screenshot](../review/viewer-tools-library-toolbar.png)). The hover line showed mesh numbers with no label.
- **A separate measure mode with its own clicks.** Rejected. A click would then mean two things, depending on a mode the person has to remember. The selection already holds the picks.
- **Send the viewer measurement with the chat message or in the selection record.** Rejected. A number from the browser would reach the agent as if a person had stated it, and the agent could repeat it as a measurement. The guidance forbids that.
- **Have the server compute every viewer measurement in the kernel.** Not chosen now. One pick already shows kernel numbers. For two picks, the mesh error was within the mesh deflection, and a server round trip on every click would delay the readout.
- **Have `read_selection` also return the kernel distance between two picks.** Deferred, not rejected. The agent would get an exact number for what the person points at, as information. It adds a field and kernel work to every two-pick selection, and no brief has needed it yet.
- **A "use this as a target" button on the readout.** Rejected for now. It would turn a viewer measurement into a requirement in one click, but no check measures the distance between two faces a person picked.
- **Draw the dimensions from the mesh bounding box.** Rejected. A mesh number drawn as a size would be a number that no check measured, styled as if a check had.
- **Add corner positions to the `extents` result, for placing the lines.** Not chosen now. It would change the check's version, so every scored variant would score again. The mesh box places the lines well enough. Revisit this if the lines and their labels visibly disagree on a real part.

## Delivery

The design note [viewer-tools.md](../design/viewer-tools.md) has the steps.

1. The readout for one or two picks, with its label.
2. The `extents` dimensions.
3. Sections.
4. Pulling a context part away from the variant.
