# CAD harness

A companion that turns what a user asks for into several engineering-checked designs to choose from. The agent proposes designs; checks it cannot change decide whether they are good.

## Language

**Brief**:
What the user asks for, in their own words, together with any images, drawings or documents they attach. Words can be added to a brief later, each one the person's own message, and none is ever edited.
_Avoid_: Spec, prompt, request

**Project**:
Everything gathered for one job: one or more briefs, their sources, and the context parts a new part must fit. A brief is created in one project and never moves to another. Variant sets, confirmed table values and the user's reviews of agent-written checks belong to the project. The web app shows a project on one page, its workspace.
_Avoid_: Job, design

**Context part**:
An existing CAD part, uploaded or read from a CAD tool, that a person confirmed into a project, such as a rail a new part clips onto, a motor or a wheel. Uploading a file confirms it. A brief uses it in one of two ways. A part the new part must fit with stays in its own frame, and the fit check measures new parts against it. A part used as a component may be placed and copied by the agent, and the scorecard says so. Its exact shape is available to build code, checks never grade it as the agent's work, and an edit may produce a new part from it. A part taken from a variant goes out of date when its slot gets a newer revision. Proposing that revision updates the part: it keeps its id and the requirements on it, and checks measure the new geometry once the person confirms it.
_Avoid_: Assembly, reference model, fixture

**Requirement**:
One checkable target taken from a brief, such as a ratio, a load, or a size limit. It quotes the words it came from, in the brief or in a file the user added to the project. It is proposed until the user confirms it. A check may measure for it before then, and the scorecard shows it as waiting on the user, with the measure beside it. A verdict rests only on a confirmed requirement, and after the user confirms, the same stored results are judged.
_Avoid_: Constraint, goal

**Hole requirement**:
A requirement for round holes, either for a metric fastener size (2 holes that fit an M5 bolt, or tapped for M4) or of a stated diameter (an 8 mm hole). A person states the size or diameter and the count, and confirms it. A hole counts when its diameter lies in the fasteners table's band for the size, or within the tolerance of the stated diameter. A stated diameter's tolerance is 0.05 mm either way unless the person states a length or picks a class of the tolerances table (H7, H8, H9, H11 of ISO 286, or ISO 2768-f, -m, -c), whose band is read by exact key and the diameter's size range. A clearance hole may name a series (close, medium or coarse), which narrows its band to that series' diameter. A group of coaxial holes, such as a counterbore, is one hole, and its diameter is the narrowest.
_Avoid_: Mounting hole, screw hole

**Wall**:
The material between a face of a part and the face across from it. Its thickness at a point is how far you go straight into the material, at right angles to the face, until you come out through a face on the far side. The `min_wall` check reports the thinnest, and a wall limit is held only when the person states one.
_Avoid_: Shell, skin

**Assumption**:
A value the agent filled in so that it could build, such as a load or a size limit the person did not state. It is stored apart from every proposal, never appears on a confirmation page, and never gets a verdict. The scorecard lists it with the measure beside the assumed value. The person turns it into a requirement by stating it.
_Avoid_: Default, guess, soft requirement

**Proposal**:
One numbered set of requirements that the agent proposed for a brief. The user confirms or declines a proposal as a whole, on a confirmation page that only the user can answer. A newer proposal never changes an older one. The server builds the next proposal from the one still waiting for the user, or from the confirmed set when none waits. A requirement leaves only when the agent names it for removal. The page shows the removal of a confirmed requirement as its own row, which takes effect when the user confirms. A declined proposal does not carry, so the agent proposes again each of its requirements that should stay.
_Avoid_: Draft, revision

**Confirmation page**:
One local web page per project, opened by the server, that lists everything waiting on the user in that project. One click confirms or declines all of it. The agent never sees its address.
_Avoid_: Elicitation, approval form

**Variant**:
One candidate design produced for a brief. The agent and the web app call it an option when they speak to the user.
_Avoid_: Candidate, design

**Variant set**:
The variants built for one brief, which the user compares side by side. A set holds at most five, one per slot. The set belongs to the brief, so confirming, editing or declining requirements removes nothing from it. A variant keeps its place in its set when a server update gives its code a new variant id.
_Avoid_: Design, batch, group, shortlist

**Slot**:
A place in a variant set, numbered 1 to 5, that keeps its number for as long as the set lives. It shows the latest revision of the variant the user is working on there.
_Avoid_: Position, index

**Body**:
One or more solids of a variant that share a name and one material, such as the four steel gears of a gear train. The build code names each solid, and the name only selects which solids a check measures. A variant of one unnamed solid has one body. A requirement can name a body by a name the user confirmed. A context part is never a body.
_Avoid_: Part, component, assembly

**Material choice**:
The material the agent picked for a slot, or for one body of it, when no confirmed requirement names one, with a one-line reason. It is a design choice, like the code: not a requirement and not a verdict. The server records it on the slot's revision, and the scorecard uses it and is labelled agent-chosen. A material the user names stays a confirmed requirement. The agent never asks the user to choose one.
_Avoid_: Default material, assumed material

**Revision**:
One signed entry in a slot's history, made when new code is built into the slot. A change the user asks for in chat adds a revision to the slot it changes and takes no new slot. Earlier revisions stay readable.
_Avoid_: Version, edit, draft

**Selection**:
The faces, edges or whole part of one revision that the user pointed at in the 3D view when they sent a message. Only the user makes one, and the server signs it. The agent reads it by its sel- id with read_selection and never makes one. It is where a change goes, never a load or a check input.
_Avoid_: Highlight, pick, annotation

**Check**:
A fixed, deterministic test of a variant against a requirement or an engineering standard, which the agent cannot change.
_Avoid_: Validator, test, verification

**Universal check**:
A check that applies to every variant whatever it is, such as building as a closed solid, interference, mass, extents (the bounding box), round holes, the thinnest wall, manufacturability, or FEA under stated loads.

**Load case**:
Where a part is held, where the load acts, and the load's force and direction, in a requirement the fea check decides. It finds regions by fixed rules that read only the geometry, never by a face the agent names, and the user confirms its words (ADR-0007). A reviewed phrase, such as "the bores of exactly 2 holes of 5.5 mm", is one our team wrote and reviewed.
_Avoid_: Boundary condition, fixture

**Described load case**:
A load case that uses a term beyond the reviewed phrases, such as "one of two flat faces that face each other across a gap". The agent combines it from a fixed list of terms before the brief has any stress result, the server writes its words, and the user confirms them. Every verdict on it is labelled described and counted apart (ADR-0007).
_Avoid_: Custom load, agent load, free-form load

**Domain check**:
A check that applies only to one kind of design, such as gear tooth strength or bolted joint preload, and comes from an engineering skill.

**Team check**:
A check our team wrote and reviewed: a universal check, the fit check, or later a domain check. Reviewed coverage and the strict pass rate count only team checks.

**Agent-written check**:
A check the agent wrote for a requirement no team check decides, before any variant of its brief exists. It is a formula with its inputs, a limit and one worked example from a cited page, with optional measuring code that runs only in the sandbox. The server's gates freeze it by its hash, and a changed check is a new check. Once the user approves it for their project on the confirmation page, its verdicts are labelled "agent-written check you approved, not reviewed by our team" and counted apart. It joins an engineering skill only after the team reviews it (ADR-0011).
_Avoid_: Generated check, custom check

**Blind rule**:
The agent may write a check for a brief only while the brief has no variants, so it cannot tune the check to a design it has seen (ADR-0011).

**Agent measurement**:
A number that the agent's own measuring code reported for a requirement no check covers. The code runs only in the sandbox. The scorecard lists the number apart from the check results, labelled "agent's own measurement, not verified". It never passes or fails anything, no team check reads it, and its requirement stays unverified (ADR-0008). Under ADR-0011 it is an agent-written check with no limit.
_Avoid_: Agent check, own check, self-check

**Viewer measurement**:
A number the web app shows for the faces and edges the user has selected in the 3D view. The browser works it out from the geometry it already holds, and the readout always ends "Measured on screen. Not a check." It never leaves the browser as data, never appears on the scorecard and never passes or fails anything. The agent reads its own exact numbers for the same selection with `read_selection` (ADR-0013).
_Avoid_: Measured dimension, viewer check

**Researched value**:
A material value the tables lack, which the agent read from a public web page or PDF datasheet. The server fetched that page, checked that the agent's quote is on it and writes the agent's number, and cites it. A check reads it only in that project. Every result and verdict that rests on it is labelled researched and counted apart (ADR-0009).
_Avoid_: Candidate value, extracted value, parsed value

**Unverified requirement**:
A requirement that no team check and no approved agent-written check decides. The scorecard always lists these.

**Engineering skill**:
A packaged body of know-how for one kind of design, bundling its domain checks, templates and sources.
_Avoid_: Plugin, module, domain pack

**Scorecard**:
All of a variant's check results, each with the formula and source behind it.
_Avoid_: Report, evaluation

**Source**:
A document, datasheet, table or standard that a requirement or check cites, either attached by the user or found by the agent. A file the user adds to a project, such as a PDF, a text file or an image, is a source the agent reads, and a requirement may quote it. A PDF the user marks as a licensed standard is a withheld source: the agent sees its name and never reads it, and a requirement may quote it only with words the user typed.
_Avoid_: Reference, citation, research

**Template**:
A family of designs controlled by parameters, which an engineering skill may bundle as a starting point for variants. The first version has none. A person changes a variant by asking in chat, and the agent edits its code.
_Avoid_: Model, generator

## Auto

**Auto run**:
The agent revising a brief's variants against the checks without stopping. The agent starts one when a scored variant fails a requirement that the user confirmed and a check decides. It revises only against those requirements, never against an assumption. It stops when every such requirement passes, when it needs a decision from the user, when the agent judges that it is stuck, or when the user presses Stop. An account's usage limit also ends a run when it refuses a build. The stop report counts the run's builds: every build the agent made under the run, once for each code, in a new slot or an old one, and whether or not it built. A build is not a revision, because a failed build adds none. There are no modes, so the user picks nothing to start a run.
_Avoid_: Auto mode, Design mode, Plan mode

**Hold**:
What a stopped Auto run puts on its web app conversation. While it holds, the server refuses every build, score and new run in that conversation. The user's next message or confirmation page answer lifts it. No tool can.

**Deeper analysis**:
Slower analysis of one chosen variant, such as full FEA and tolerance stack-ups. It runs when the user asks about that variant or a requirement needs it. It is not a mode.
_Avoid_: Test mode, verify mode, analysis mode
