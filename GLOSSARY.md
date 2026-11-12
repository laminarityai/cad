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
An existing CAD part, uploaded or read from a CAD tool, that a person confirmed into a project, such as a rail a new part clips onto. Checks measure new parts against it, and an edit may produce a new part from it. A part taken from a variant goes out of date when its slot gets a newer revision. Proposing that revision updates the part: it keeps its id and the requirements on it, and checks measure the new geometry once the person confirms it.
_Avoid_: Assembly, reference model, fixture

**Requirement**:
One checkable target taken from a brief, such as a ratio, a load, or a size limit. It quotes the words of the brief it came from. It is proposed until the user confirms it. A check may measure for it before then, and the scorecard shows it as waiting on the user, with the measure beside it. A verdict rests only on a confirmed requirement, and after the user confirms, the same stored results are judged.
_Avoid_: Constraint, goal

**Hole requirement**:
A requirement for round holes, either for a metric fastener size (2 holes that fit an M5 bolt, or tapped for M4) or of a stated diameter (an 8 mm hole). A person states the size or diameter and the count, and confirms it. A hole counts when its diameter lies in the fasteners table's band for the size, or within a tolerance of the stated diameter. A group of coaxial holes, such as a counterbore, is one hole, and its diameter is the narrowest.
_Avoid_: Mounting hole, screw hole

**Assumption**:
A value the agent filled in so that it could build, such as a load or a size limit the person did not state. It is stored apart from every proposal, never appears on a confirmation page, and never gets a verdict. The scorecard lists it with the measure beside the assumed value. The person turns it into a requirement by stating it.
_Avoid_: Default, guess, soft requirement

**Proposal**:
One numbered set of requirements that the agent proposed for a brief. The user confirms or declines a proposal as a whole, on a confirmation page that only the user can answer. A newer proposal never changes an older one.
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

**Material choice**:
The material the agent picked for a slot when no confirmed requirement names one, with a one-line reason. It is a design choice, like the code: not a requirement and not a verdict. The server records it on the slot's revision, and the scorecard uses it and is labelled agent-chosen. A material the user names stays a confirmed requirement. The agent never asks the user to choose one.
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
A check that applies to every variant whatever it is, such as building as a closed solid, interference, mass, extents (the bounding box), round holes, manufacturability, or FEA under stated loads.

**Domain check**:
A check that applies only to one kind of design, such as gear tooth strength or bolted joint preload, and comes from an engineering skill.

**Agent-written check**:
A check the agent drafted for a requirement no existing check covers. Its results count as unverified until the user reviews it for their project, and it joins an engineering skill only after the team reviews it.
_Avoid_: Generated check, custom check

**Agent measurement**:
A number that the agent's own measuring code reported for a requirement no check covers. The code runs only in the sandbox. The scorecard lists the number apart from the check results, labelled "agent's own measurement, not verified". It never passes or fails anything, no check or formula reads it, and its requirement stays unverified (ADR-0008).
_Avoid_: Agent check, own check, self-check

**Researched value**:
A material value the tables lack, which the agent read from a public page. The server fetched that page, checked that the agent's quote is on it and writes the agent's number, and cites it. A check reads it only in that project. Every result and verdict that rests on it is labelled researched and counted apart (ADR-0009).
_Avoid_: Candidate value, extracted value, parsed value

**Unverified requirement**:
A requirement that no reviewed check covers. The scorecard always lists these.

**Engineering skill**:
A packaged body of know-how for one kind of design, bundling its domain checks, templates and sources.
_Avoid_: Plugin, module, domain pack

**Scorecard**:
All of a variant's check results, each with the formula and source behind it.
_Avoid_: Report, evaluation

**Source**:
A document, datasheet, table or standard that a requirement or check cites, either attached by the user or found by the agent.
_Avoid_: Reference, citation, research

**Template**:
A family of designs controlled by parameters, which an engineering skill may bundle as a starting point for variants. The first version has none. A person changes a variant by asking in chat, and the agent edits its code.
_Avoid_: Model, generator

## Modes

**Mode**:
A setting on the conversation that decides what the agent does next and when it hands back to the user.

**Design mode**:
The default mode. A new brief builds at once: the agent makes variants, runs checks, shows scorecards, and stops for the user to pick a variant or ask for a change. There is no Plan mode, because nothing waits for a confirmation before it builds.

**Auto mode**:
The agent revises variants against the checks without stopping, until every requirement passes, it needs a decision from the user, or it judges that it is stuck. An account's usage limit also ends a run when it refuses a build.

**Deeper analysis**:
Slower analysis of one chosen variant, such as full FEA and tolerance stack-ups. It runs when the user asks about that variant or a requirement needs it. It is not a mode.
_Avoid_: Test mode, verify mode, analysis mode
