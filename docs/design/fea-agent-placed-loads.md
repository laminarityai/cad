# Load faces that agent-written code places

Status: design, not built. The operator approved agent-written code that picks the support and load faces for the `fea` check on 2026-11-12, with the words "the agent can write any code for tests we do not have" and "let's not get hung up on specific cases". This note settles how. The text of the ADR-0007 amendment it needs is in [ADR-0007](../adr/0007-a-load-names-anchors-never-faces.md), dated 2026-11-12.

Each claim carries one of three labels. "Measured" cites the note that measured it. "Read" cites the file it was read from, at origin/main 896f43a. "Inferred" is reasoning that no run has tested. A claim that needs a run is marked "not measured", and build step 1 takes it.

## What the terms leave undecided

Measured ([load cases the agent describes](fea-described-loads.md), What it decides): the described terms decide 2 of the 12 stuck corpus parts (`hook` and `sb_l_bracket`) and 3 of the 6 novice briefs (the shelf, the clamp and the wall bracket). Of what is left, two need a new way to say where the part is held and loaded:

- `equal_angle` needs a support on one leg's face. No term names a leg.
- `sb_gusset` needs the person to say which edge is held. A triangle has no ends a rule can find.

The rest need something this note does not add. `sb_arm`, the lid and a rail hook rest or pivot. The 7 parts at the large-displacement gate need a nonlinear solve or a smaller force. The snap arm needs a displacement load. So the first claim to test is how much code placement adds beyond these two parts. It is not measured, and build step 1 measures it.

## What any design must keep

These hold today, and this design keeps each one.

- The agent's code never sees a stress result of the brief. Today the result rule enforces this for described load cases (read, `src/cad/briefs/described.py` `check_proposed`).
- No agent code runs beside the solver. The `fea` check runs only team code, in the analysis image (read, `src/cad/sandbox/image.py`, ADR-0005).
- The frame does not matter. The scored variant is turned by a container that runs only team code before agent code sees it (read, `src/cad/agent_checks/turned.py`).
- Freedom the person's words leave goes to the worst case. Ties are solved and the worse result kept (read, ADR-0007).
- A count that does not match, or more candidates than `anchors.CANDIDATE_LIMIT`, gives `unknown` (read, `src/cad/checks/container/anchors.py`).
- Every verdict that rests on agent work is labelled and counted apart (read, ADR-0009, ADR-0011).

## 1. Code picks faces, and the reviewed `fea` check solves

**Pick.** The agent writes a placement. A placement is a frozen record that holds build123d code. The code receives the stored part and returns support and load faces. The server turns the faces into kernel face indices. The reviewed `fea` check reads the indices from its request wire, builds its regions from them, and runs the same mesh, solve and gates it runs for a reviewed phrase. No agent code runs in the `fea` job.

**Cost.** The agent chooses where the load goes, which ADR-0007 was written to forbid. The gates in question 4 narrow that choice. They do not close it, and this design does not claim they do.

Options weighed:

- **A placement that feeds the reviewed check.** Picked. Everything after `anchors.resolve` stays as it is: `mesh_pair`, `_unmatched`, `solve_at` on the coarse and the fine mesh, the keep-out, and `judged` with its 3% mesh-change gate and 5% large-displacement gate (read, `src/cad/checks/container/fea.py`). The agent-written-check machinery already runs build123d code on a stored shape in the build image, turns it in a team-only container, and stores the run signed by check version and brep sha (read, `src/cad/agent_checks/harness.py`, `turned.py`, `runs.py`). A placement reuses all of it.
- **An agent-written check that calls the solver.** Rejected. The build image has no gmsh or CalculiX, and the analysis image runs only team code (read, `src/cad/sandbox/image.py`). Agent code in the solver's process could read the solution before it returns faces. The formula grammar and the worked-example gate of ADR-0011 test a closed-form result against a cited page, and an FEA verdict has neither (read, `src/cad/agent_checks/gates.py`).
- **Raw face indices in the load case.** Rejected. Indices belong to one revision. Auto makes a new revision without the person, so every revision would need new indices, which the operator ruled out for the person (#79) and which the agent would then pick per revision.
- **A selector grammar, or a new term for each stuck part.** Rejected. A nested grammar is the option the described-loads note already set aside, and a term per part is what the operator ruled out on 2026-11-11 and again on 2026-11-12.

The placement is its own record, not a new kind of `AgentCheck`. Adding a `kind` field to `CheckDraft` would change every stored check's sha256 unless the field defaulted, and a placement shares no field with a check beyond the code and the probe (read, `src/cad/agent_checks/model.py`). It lives in `src/cad/agent_checks/placement.py` and is stored at `projects/<pid>/placements/<n>` with the same signed-record helper that `store.freeze` uses. One directory still owns all agent-written code.

## 2. The code reads the part and returns faces

**Pick.** These are the types.

```python
# src/cad/agent_checks/placement.py, on the host.
MAX_PLACEMENTS_PER_BRIEF: Final = 4

class PlacementDraft(Frozen):
	brief_id: str
	account: str
	"""The agent's words for where the part is held and loaded. The page shows them as the
	agent's words, beside the words the server writes."""
	code: Annotated[str, Field(min_length=1, max_length=MAX_CODE_CHARS)]
	"""build123d. Defines `place(part)`, which calls `candidate(support=..., load=...)`."""
	probe: Annotated[str, Field(min_length=1, max_length=MAX_CODE_CHARS)]
	"""build123d code for one sample shape, as `CheckDraft.probe`."""

class Placement(Frozen):
	number: int
	draft: PlacementDraft
	sha256: str

# In the sandbox, from the team preamble that harness.py writes.
def candidate(support: Iterable[Face], load: Iterable[Face]) -> None: ...

# What a run returns, after the preamble maps each Face to its index.
@dataclass(frozen=True, slots=True)
class PlacedCandidate:
	support: frozenset[int]
	load: frozenset[int]

@dataclass(frozen=True, slots=True)
class Placed:
	candidates: tuple[PlacedCandidate, ...]

# src/cad/loads/model.py: one new support kind and one new load kind.
class PlacedSupport(Frozen):
	kind: Literal["placed"] = "placed"
	placement: Sha256

class PlacedLoad(Frozen):
	kind: Literal["placed"] = "placed"
	placement: Sha256
	direction: Direction
```

The code reads only `part`, the stored shape as a build123d `Part`, and the build123d names. It does not get the brief, the requirement, any result, the other variants, the context parts or the network. The harness already gives this much and no more (read, `src/cad/agent_checks/harness.py`). `place(part)` calls `candidate` 1 to `CANDIDATE_LIMIT` times. Each call names a nonempty support and a nonempty load that share no face. Every candidate is solved and the worst kept, so code that cannot tell two faces apart returns both.

The preamble maps each returned `Face` to its position in the kernel's explorer order by `IsSame`, with the same explorer the kernel's `faces` uses (read, `src/cad/checks/container/kernel/ocp_kernel.py`). The analysis image is built on the build image, so both read the brep with the same OCCT (read, `src/cad/sandbox/image.py`, `base=BUILD`). It is not measured that the two images give the same order for the same bytes. Build step 1 measures it on the corpus.

A `LoadCase` with a placed support needs a placed load with the same `placement`, and the reverse. The pairing validator in `LoadCase` enforces this, as it does for described pairs (read, `src/cad/loads/model.py`). One placement places both ends. A placed support with a described load is refused, because a described load reads its supports from a term.

The direction stays a term the server writes words for: `Along`, `Across`, `AnyWay`, `Into` or `Away`. `Into` needs a load region of one flat face, or of coplanar flat faces, because it presses along that face's normal. The force is the person's number, from the requirement (read, `src/cad/scorecard/requirements.py` `demand`).

In the analysis image a new resolver, `placed.resolve`, builds each `Candidate(support, load, basis)` from the indices. A flat face gets a `Plane` patch and a round face gets a `Bore` patch, with its axis and radius, so `region_faces` and its lies-on test work unchanged and a round support gets the keep-out a bore gets (read, `src/cad/checks/container/regions.py`, `elastic.py`, `fea.py` `_near`). A face whose surface is `Curved` has no patch, so a placement that names one gives `unknown`, and the reason names the face. The cost is that a load on a fillet or a spline face is not checked. Build step 1 counts how often the stuck parts need one.

`OnLargestFlat(middle)` has no placed form. A press in the middle of a face is a placement whose load is the disc that `described.disc` already builds, offered as `middle=True` on `candidate` for a load of one flat face. This is the one extra the preamble takes, because the disc is not a face and code cannot return it.

## 3. Written until the brief's first stress result

**Pick.** The result rule, the same rule as described load cases. `write_placement` takes a `brief_id` and is refused once any variant of the brief has a stored `fea` result, whatever its verdict (read, `src/cad/variant_sets/stressed.py` `has_stress_result`). `check_proposed` treats a placed load case as it treats a described one. It refuses a new one after the first result, and it refuses a proposal that drops one the person has not declined. The rule reads "described or placed" through one property, `LoadCase.agent_made`.

**Cost.** The code is written knowing the shapes of the variants that exist. It can be fitted to them. It is never written knowing a stress result. The blind rule of ADR-0011 would send every load stated after the options are built ("will it hold 5 kg?") back to not checked, which is the common path the result rule was chosen to keep (read, ADR-0007 amendment of 2026-11-11). Seeing the variants is also what lets the person see the placed faces on them (question 5). This contradicts ADR-0011's blind rule for this record. The ADR-0007 amendment says so.

There is no edit, as for an agent-written check. A changed placement is a new record with a new sha256, so it is a new load case, and the result rule applies to it.

## 4. The gates

**Pick.** Six gates, three of them new. Each runs in a fixed place, and the order below is the order they run.

Carried over from ADR-0011:

1. **The result rule** replaces the blind rule (question 3). It runs in `write_placement` and again in `check_proposed`.
2. **Form.** The code is at most `MAX_CODE_CHARS`, compiles, and defines `place`. The probe builds a solid. On the probe, `place` returns 1 to `CANDIDATE_LIMIT` candidates, each with a nonempty support and a nonempty load that share no face. A brief holds at most `MAX_PLACEMENTS_PER_BRIEF` placements, as `MAX_CHECKS_PER_BRIEF` caps checks (read, `src/cad/agent_checks/model.py`).
3. **Repeat and turn.** On the probe at write time and on every scored variant, the code runs twice. Once on the stored shape, and once on a copy that a team-only container turned and moved by a `Motion.drawn()` the agent cannot compute (read, `turned.py`, `harness.py`). The two runs must return the same indices. If they differ, the requirement is `unknown`, and the reason says the placement depends on the frame. It is not measured that a turned and moved copy keeps the explorer order. Build step 1 measures it. If it does not, the turned run's faces are mapped back by `IsSame` on the untransformed shape in the team-only container.

Dropped, because they test a formula and a placement has none: Units and the worked example.

New:

4. **Bounded area.** Team code in `placed.resolve` refuses a support or a load whose faces cover more than `MAX_REGION_SHARE` of the part's surface area, and the requirement is `unknown`. Holding most of a part, or spreading the load over most of it, can make any part pass. The constant starts at 0.5. Build step 1 sets it to the largest share that any reviewed or described candidate covers on the corpus, so no case a term already decides is refused by it. Not measured.
5. **Mirror.** This gate is the defence against code that picks the less harmful of two faces that look the same. For a support or a load that is one face, or the bores of one hole, team code in `placed.resolve` finds its look-alikes. A look-alike face has the same surface kind, an area within 1%, and for a round face a radius within 1%. A look-alike hole has a diameter within 1%. For each look-alike support s' and look-alike load l' whose centroid distance is within 1% of the placed pair's, and whose angle between normals or axes is within 1° of the placed pair's, the pair (s', l') joins the candidates. The worst is kept. More than `CANDIDATE_LIMIT` candidates gives `unknown`, as for a term. On `equal_angle`, code that holds leg A's face and loads leg B's tip gets leg B's face and leg A's tip as a second candidate (inferred). On a part that is truly symmetric the mirror gives the same result, so the gate costs only a solve. On a part that is not, the mirror is the case the code might have avoided. The 1% and 1° bands are the bands `described.py` uses (read, `src/cad/checks/container/described.py` `TIE_FRACTION`, `FACING_TOL_RAD`).
6. **Drift.** This gate is the defence against code that picks differently on a revision the person never saw. For each candidate, team code reports a signature: the number of faces of each surface kind in the support and in the load, and the lever, which is the distance between the support and load centroids as a fraction of the part's reach. The first `fea` result on each slot under a placement stores it. On every later revision of that slot, the request carries the stored signature. A different face count by kind, or a lever below 0.9 of the stored one, gives `unknown`, and the reason says the placement picked a different kind of place than before. The 0.9 is inferred, not measured. Build step 4's live walk reports how often an honest Auto revision trips it.

What stays undefended. The design does not claim to close these.

- **A choice between places that do not look alike, on the variants the person saw.** If the code holds the stiff end and loads the near face, the person sees exactly that, highlighted (question 5). The person's approval is the only defence.
- **A trigger that keeps the signature.** Code that picks a different face of the same kind at the same lever, keyed on a feature count or a tag the agent builds into a later revision.
- **Mirror on multi-face regions.** A support of several faces that are not one hole gets no look-alikes.
- **The account.** The words beside the highlights are the agent's account of the code. The server writes only the force and direction words.
- **The front-loaded path.** When the load is stated with the brief, no variant exists at approval, so the person sees the faces only on the agent's probe (question 5).

Considered and rejected: a run on a copy scaled by a secret factor. It catches code keyed on an exact size. It also refuses honest code that holds "the holes of 5.5 mm" because the person said M5, and the person sees what such code picks on the seen variants. The drift gate covers the case that matters, a pick that changes after approval.

## 5. The person sees the faces and approves

**Pick.** A new confirmation page item kind, `placement`, beside the requirement it serves, answered with the same single Confirm (read, `src/cad/confirmations/items.py`, `registry.py`, and `agent_checks.py` for the pattern). It shows:

- the server's words for the load case, with the force and the direction;
- the agent's account, marked "the agent's words";
- a link per slot to its latest revision in the workspace's 3D view, with the held faces and the loaded faces highlighted in two colors, from the write-time placement run on that revision;
- when no variant exists, the probe in the same view, and the line "No option is built yet. You are seeing the agent's sample shape. Each option's scorecard shows where it was held and loaded."

The 3D view highlight is build step 3 of the described-loads note, which adds the deciding candidate's faces to the `fea` result. That work is in progress on another branch and not on main (read, origin/main 896f43a). A placement reuses its highlight with the indices from the placement run. It is not measured that the viewer's face index (read, `src/cad/geometry/container/topology.py`, build123d `faces()` order) equals the kernel's explorer order. Build step 1 measures it.

Approval means "these are the faces I meant". It does not mean the code is right. Declining the placement leaves the requirement unverified, as declining an agent-written check does (read, ADR-0011).

**Label.** A verdict reads "load placed by agent-written code you approved, not reviewed by our team". The agent reports a pass as "passes on a load my code placed". The scorecard's `fea` row shows the deciding candidate's faces on every scored variant, so a person who saw only the probe can still see where each option was held and loaded.

**Cost.** A link to the 3D view is one click away from the page, not on it. A second confirmation after the first build, with the faces on real options, would close the front-loaded gap. It was rejected because it adds a stop for the person on every brief with a load stated up front.

## 6. Labelled and counted apart from described

**Pick.** A third value on the scorecard: `Checked.load_case: Literal["described", "placed"] | None` (read, `src/cad/scorecard/model.py`). A placed verdict is never also counted as described, because one placement places both the support and the load.

- **Auto.** A pass on a placed load case counts toward the stop when every requirement passes, and a fail is revised against, as for described cases. `Standing.placed` and `AllPass.placed` join `Standing.described` and `AllPass.described`, and the stop report names the placed passes. There is no new `Mark`, as described cases have none (read, `src/cad/auto/model.py`).
- **The tracer.** `By.PLACED`, "a team check on a load case agent-written code placed", outside `REVIEWED`, with a `placed_coverage` share beside `described_coverage`. In `by_of`, placed takes precedence over described and described over researched (read, `evals/briefs/tracking.py`).

**Cost.** Three ways a `fea` verdict can be labelled. Folding placed into described would be simpler, and it would make code nobody can read look like server-written words.

## 7. The code has its own budget, outside the solve

**Pick.**

- Each placement run has the harness's `WALL_SECONDS` of 30 s, and the turn has `TURN_SECONDS` of 60 s (read, `harness.py`, `turned.py`). A run that times out gives `unknown`.
- Each scored revision runs the code twice, plain and turned. Each run is stored signed by placement sha256 and brep sha, so a revision's run happens once (read, `runs.py`). Both runs happen before the `fea` job is queued and outside its `BUDGET` of 600 s (read, `fea.py`).
- The code returns at most `CANDIDATE_LIMIT` candidates, 4, and mirror candidates count toward the same 4. Measured ([load cases the agent describes](fea-described-loads.md), What it decides): a candidate takes about 3 to 100 s to mesh and solve, and the two heaviest corpus parts took 203 s and 451 s for 2. So 4 candidates fit at up to about 150 s each.

**Cost.** Scoring a variant with a placed load case waits up to about 90 s more before the `fea` job starts (inferred, from the two limits). Code that returns 4 candidates on a part with a look-alike gets `unknown`.

This order runs agent code before a team check, where ADR-0011 runs measuring code after the team checks. The placement run sees no result, so the reason for that order still holds (inferred).

## 8. Build steps

Each step is one PR and ends in a check that passes or fails.

1. **Measure.** No product code. Write placement code by hand, as the agent would, for `equal_angle`, `sb_gusset` with each edge the person might name, and each novice brief the terms do not decide. Run it through the analysis image with today's solver by passing the indices as a test resolver. Report each part's verdict and candidates. Also measure:
   - that the build and analysis images give the same explorer order for the same brep bytes, on all 20 corpus parts;
   - that a turned and moved copy keeps the explorer order;
   - that the viewer's face index equals the kernel's;
   - the largest surface share of any reviewed or described candidate on the corpus, which sets `MAX_REGION_SHARE`;
   - the mirror candidates on each part, and whether any goes over 4;
   - how many stuck parts need a `Curved` face.

   The check is a script whose output table the PR commits. If code placement decides no part beyond the two the terms leave, the PR says so and the rest stops.
2. **The `fea` side.** `PlacedSupport` and `PlacedLoad` on the wire, `placed.resolve`, the bounded-area, mirror and drift gates, and the signature in the result. The check is harness cases in the container tests: a mirrored angle gives 2 candidates, a support over the share gives `unknown`, a changed signature gives `unknown`, and the reviewed corpus scores the same as on main.
3. **The record and the tool.** `PlacementDraft`, `Placement`, the store, `write_placement` with the result rule, Form and the probe's repeat-and-turn, and the run on each scored variant before its `fea` job. `check_proposed` reads `LoadCase.agent_made`. GLOSSARY gains "Placed load case". The check is the operation's tests and one `cad-call` walk that writes a placement and scores `equal_angle`.
4. **What the person and the counts see.** The `placement` page item with the highlight links, the label on the scorecard and in the web app, `Standing.placed` and `AllPass.placed`, `By.PLACED`, and the tool guidance. The check is the web tests and one live walk through the app: a brief that needs a leg held, an Auto run to its stop, and a screenshot of the page item and the labelled verdict.

## Out of scope

- Supports that rest, slide or pivot ([#254](https://github.com/laminarityai/cad/issues/254)).
- Loads given as a displacement.
- The large-displacement gate ([#260](https://github.com/laminarityai/cad/issues/260)).
- Sizing the mesh to a pressed disc.
- A term or rule for one part.

## Single cases, decided here

- **`sb_gusset`.** The person's words say which edge is held. The agent writes code for that edge, and the person sees it highlighted. If the person's words do not say, the code returns each edge face that could be held as its own candidate, and the worst is kept.
- **`equal_angle`.** The code holds one leg's face and loads the other leg's tip. The mirror gate adds the swapped pair.
- **A placement that also matches a term.** Nothing stops it. The described terms stay, and the tool guidance tells the agent to use a reviewed phrase first, then a described term, then a placement, because each later one is labelled further from the team's review.
