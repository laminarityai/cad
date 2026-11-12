# Load cases the agent describes

On 2026-11-11 the operator asked why the `fea` check can be told where a part is held and loaded only through five fixed phrases, and said to modify ADR-0007 so that the agent works for general CAD cases. This note weighs four ways to do that against the corpus of [fea load anchors](fea-load-anchors.md) and six briefs a novice might write. It recommends one and gives its data shape, rules, tests and build order. The operator approved the recommendation on 2026-11-11 with three decisions, recorded in the last section. [ADR-0007](../adr/0007-a-load-names-anchors-never-faces.md) carries the amendment. Option A of fea load anchors is approved and being built, and this note treats its rules as the rules behind the five phrases.

## What the five phrases cannot say

The five phrases are three supports ("the bores of exactly n holes of d mm", "its largest flat face", "the flat face at one end of its long axis") and two loads ("the end farthest from the supports", "exactly n holes of d mm that are not supports").

The corpus holds 19 parts. 11 stop on an anchor today. Option A fixes 7 of them. These 4 are left:

| Part | Brief | Why the phrases miss it |
|---|---|---|
| `equal_angle` | one leg fixed, 20 N at the end of the other | The long axis is the diagonal, 45° from each leg's end, outside A's 30° cone. |
| `sb_gusset` | a triangle fixed at one end, 20 N at the other | A triangle has no flat end. |
| `sb_arm` | a lever pinned through one end hole, 20 N at the other | Both end holes are 28 mm, so "exactly 1 hole of 28 mm" finds 2. |
| `sb_l_bracket` | screwed to the wall through 2 holes | Each leg has 2 holes of 5.1 mm, so "exactly 2" finds 4. |

4 more parts resolve and then stop at the large-displacement gate. That is not an anchor problem, and this note does not change it.

The six novice briefs:

| Brief | Where it is held | Where the load acts | Phrase today |
|---|---|---|---|
| A shelf pressed in the middle | screwed through its back, or resting on two brackets | a small area at the middle of the top | none |
| A hook hung from a rail | the curl that rests on the rail | the curl the weight hangs from | none |
| A clamp | one jaw | the other jaw, pressed apart by what it grips | none |
| A lid pushed down | the rim that sits on the box | the middle of the top | none |
| A bracket bolted to a wall through a face | the holes in its back face | its far end | only when no other face has holes of that size |
| A snap arm bent at its tip | the body | the tip, by a displacement | none |

## What any route must keep

These were decided before this note:

- The agent never decides whether a design is good, and nothing lets it place a load where it does least harm on a variant whose stress result it has seen.
- No per-revision face picking. Auto runs without a person step for each revision.
- The person states intent and confirms targets, and the agent decides the rest.
- By analogy with agent-written checks, what the agent authors is confirmed by the person, labelled and counted apart. The draft of this note also took their timing, so nothing new was written once a brief had variants. On 2026-11-11 the operator replaced that with the result rule, under which nothing new is written once the brief has a `fea` result.

Each route below is judged on six properties. It must be frame-free. It must be written before any `fea` result of the brief exists. The person must confirm plain words. Ties must go to the worst case. A description that does not resolve must fail closed to `unknown` with a reason. The agent must not be able to change it after seeing a result.

## Options

### 1. Terms the agent composes, words the server writes

The agent picks a support term, a load term and a direction from a closed list. Fixed code in `fea` resolves each term on the geometry. The server writes the words the person confirms from the terms, with the same function that writes the five phrases now.

Each term reads only normals, principal axes, centroids, areas, hole axes and the mouths of holes, so the route is frame-free. The words are a function of the terms, so the person reads what the check runs. The cost is that a brief the list cannot express stays unverified until a term is added.

### 2. The faces a confirmed context part touches

The person confirms a wall, a rail or a box as a context part, and the support is the faces of the variant within a small distance of it.

The words are the plainest of any route ("where it touches the rail"). But the agent builds the variant and sets where it sits in the context part's frame, so the agent sets the contact and with it the faces that are held. That is the choice ADR-0007 exists to take away. It also needs a wall or a rail as a part, which the person rarely has, and an `fea` job holds no context part today. Not chosen.

### 3. Agent-written code that picks the faces

The agent writes a function that returns the support and load faces. It is gated like an agent-written check. It is written before the brief has variants, frozen by its sha, approved by the person, and run again under a secret rigid motion.

This covers any face a term cannot name. But code can single out any face, by its area or by a feature the agent builds later. The person cannot read code, so the words on the page would be the agent's account of the code, not what runs. A run on a turned and moved copy shows that the code ignores the frame. It cannot show that the code did not choose the least harmful face. An agent-written check also chooses where it measures, and its defence (written blind, run turned, labelled) is weaker than ADR-0007's rule. Here a reviewed check already exists, and choosing where its load goes is the thing ADR-0007 forbids. Not chosen now. The operator decides after build step 1 reports what the terms cover, measured on the corpus and the novice briefs.

### 4. Reviewed phrases plus described load cases

Route 1, with the five phrases kept as the reviewed base. A load case that uses any new term is a described load case. Its verdicts are labelled and counted apart, as researched values are.

### Also weighed: a describer that sees only the person's words

A second model call on the server reads the brief's words and the person's notes, never a variant or a result, and writes the terms. The terms are then always written without sight of a design or a result, so a new description after the brief has a stress result could be written too. Not chosen now. The result rule already serves a load stated after variants exist, so the describer adds only the case after a stress result. It adds a model call to every proposal with a load and a second model to the path of every verdict on a load. It is the way to lift that limit in [What it does not cover](#what-it-does-not-cover) if the operator wants it lifted.

### Compared

| | 1. Terms | 2. Contact | 3. Code | 4. Phrases and terms |
|---|---|---|---|---|
| Frame-free | each term | yes | only as far as a turned run tests | each term |
| Before any stress result | server refuses later | yes | the first gate refuses later | server refuses later |
| Words the person confirms | written by the server from what runs | plain | the agent's account | written by the server from what runs |
| Ties to the worst | every term gives candidates | needs a rule | only if the code does it | every term gives candidates |
| Fails closed | per term | no contact gives `unknown` | only if the code does it | per term |
| No change after a result | frozen in the load case | frozen | frozen by sha | frozen in the load case |
| Who sets where the load goes | the terms and the geometry | the agent, through the pose | the agent's code | the terms and the geometry |
| Novice briefs decided (inferred) | 4 of 6 | needs a part for the wall or rail | 4 of 6, since every support is still fixed and every load a force | 4 of 6 |
| Existing verdicts | all become described | unchanged | unchanged | unchanged |

## Recommendation

Route 4. Keep the five phrases as the reviewed base and add a closed list of terms that the agent composes into a described load case before the brief has any `fea` result. The server writes its words, the person confirms them, fixed code in `fea` resolves them, and every verdict on one is labelled and counted apart. Routes 1 and 4 are the only ones where the agent chooses neither faces nor code and the person reads words that are exactly what the check runs. Route 4 also leaves every verdict on a reviewed phrase as it is.

The list is flat on purpose. No term takes another term as input, except that a load term reads the support. Nesting would let a chain of relations single out one face, and its words would grow past what a person reads. A new term needs evidence and a harness case, as a new phrase does. A new pairing of terms needs neither, which is the difference from option B.

## Data shape

A sketch for `src/cad/loads/model.py`. The existing kinds and their wire forms do not change, so the id of every stored load case stays the same.

```python
class PartAxis(StrEnum):
    MIDDLE = "middle"  # the principal axis of second-largest spread
    SHORT = "short"  # the principal axis of least spread; LONG stays the reviewed flat_end


class Curve(StrEnum):
    HOLE = "hole"  # the bores of one hole, grouped as the anchors group them now
    INNER_CURVE = "inner_curve"  # a concave cylindrical face that is not part of a hole


# Supports the agent may describe. Every support is fixed, as now.
class EndOf(Frozen):
    """The flat face across one end of its middle or short axis."""

    kind: Literal["end_of"] = "end_of"
    axis: PartAxis


class Facing(Frozen):
    """One of two flat faces that face each other across a gap."""

    kind: Literal["facing"] = "facing"


class Each(Frozen):
    """One hole or one inner curve, of this diameter when given. Each one is a candidate."""

    kind: Literal["each"] = "each"
    curve: Curve
    diameter: Length | None = None


class InOneFlatFace(Frozen):
    """Exactly `count` holes that open on one flat face. Each such set of holes is a candidate."""

    kind: Literal["in_one_flat_face"] = "in_one_flat_face"
    count: HoleCount
    diameter: Length | None = None


type Support = Annotated[
    Holes | LargestFlat | FlatEnd | EndOf | Facing | Each | InOneFlatFace,
    Field(discriminator="kind"),
]


class Into(Frozen):
    """Along the inward normal of the loaded flat face: a press."""

    kind: Literal["into"] = "into"


class Away(Frozen):
    """Along the line from the support's centroid to the load's centroid: a pull."""

    kind: Literal["away"] = "away"


type Direction = Annotated[Along | Across | AnyWay | Into | Away, Field(discriminator="kind")]


# Loads the agent may describe.
class OnLargestFlat(Frozen):
    kind: Literal["on_largest_flat"] = "on_largest_flat"
    middle: bool = False  # on a disc at the middle of the face, not the whole face
    force: Force
    direction: Direction


class OnOpposite(Frozen):
    """On the flat face across the gap from a `Facing` support."""

    kind: Literal["on_opposite"] = "on_opposite"
    middle: bool = False
    force: Force
    direction: Direction


class OnFarthest(Frozen):
    """On the hole or inner curve farthest from the supports, of this diameter when given."""

    kind: Literal["on_farthest"] = "on_farthest"
    curve: Curve
    diameter: Length | None = None
    force: Force
    direction: Direction


type Load = Annotated[
    FarEnd | OnHoles | OnLargestFlat | OnOpposite | OnFarthest, Field(discriminator="kind")
]

REVIEWED: Final = frozenset(
    {"holes", "largest_flat", "flat_end", "far_end", "on_holes", "along", "across", "any"}
)


class LoadCase(Frozen):
    support: Support
    load: Load

    @property
    def described(self) -> bool:
        """True when the case uses a term beyond the reviewed phrases."""
        return not {self.support.kind, self.load.kind, self.load.direction.kind} <= REVIEWED
```

A validator on `LoadCase` refuses three pairings at parse:

- `OnOpposite` without a `Facing` support.
- `Into` on any load but `OnLargestFlat` and `OnOpposite`.
- `Axis.HOLE_AXIS` without a hole support (`Holes`, `Each` of holes, or `InOneFlatFace`), as now.

`id` and `unit_case` keep their definitions. The wire module in the container gains a TypedDict for each new kind.

## Words

`describe_case` keeps its order. The load comes first, then the direction, then the support.

| Term | Words |
|---|---|
| `EndOf(MIDDLE)` | held by fixing the flat face at one end of its middle axis |
| `Facing` | held by fixing one of two flat faces that face each other across a gap |
| `Each(HOLE, 28 mm)` | held by fixing the bore of one hole of 28 mm, whichever is worse |
| `Each(INNER_CURVE)` | held by fixing one inner curved face, whichever is worse |
| `InOneFlatFace(2, 5.1 mm)` | held by fixing the bores of exactly 2 holes of 5.1 mm that open on one flat face, whichever face is worse |
| `OnLargestFlat(middle)` | 20 N on the middle of its largest flat face |
| `OnOpposite` | 20 N on the flat face across the gap from the supports |
| `OnFarthest(INNER_CURVE)` | 20 N on the inner curved face farthest from the supports |
| `OnFarthest(HOLE, 28 mm)` | 20 N on the hole of 28 mm farthest from the supports |
| `Into` | pressing into the face |
| `Away` | pulling straight away from the supports |

A hook hung from a rail reads "50 N on the inner curved face farthest from the supports, pulling straight away from the supports; held by fixing one inner curved face, whichever is worse".

## Resolution rules

The rules are fixed code in `checks/container/anchors.py`, pure functions over the kernel's face summary, as now.

| Term | Faces it finds | Candidates | `unknown` when |
|---|---|---|---|
| `EndOf(axis)` | Option A's flat-end rule, on the middle or short principal axis | One per end. Where two axes tie, one per end of each | Neither end has a face that passes the rule |
| `Facing` | Pairs of flat faces whose outward normals are within 1° of opposite, each in front of the other, with the midpoint of their centroids outside the material (a new kernel query) | Each face of each pair | No pair |
| `Each(curve, d)` | Every hole, or every inner curve, of diameter d within the anchors' diameter tolerance when d is given. Coaxial inner-curve faces of one radius are one curve | One per match | No match |
| `InOneFlatFace(n, d)` | For each flat face, the holes of diameter d whose mouths the kernel lists among that face's openings | One per distinct set of holes | No face has such a hole, or some face has a number other than n |
| `OnLargestFlat` | The flat faces of largest area, within 1%, that are not support faces | One per face | Every such face is a support face |
| `OnOpposite` | The face that the `Facing` support faces | One | Never, because `Facing` found the pair |
| `OnFarthest(curve, d)` | Matches that are not support faces, whose centroids lie farthest from the support's centroid, within 1% | One per match | No match outside the support |
| `middle` | A disc patch on the face, centred on its centroid, of radius 0.1 × √(face area) | No new ones | The face's triangles that lie wholly in the disc cover under half its area |
| `Into` | One unit load along the loaded face's inward normal | No new ones | Never, because parsing allows it only on a flat face |
| `Away` | One unit load along the line from the support's centroid to the load's | No new ones | The two centroids are closer than 1% of the part's reach |

These rules hold for every term:

- A candidate is one support region with one load region. The check solves every candidate over the direction's subspace and keeps the worst result, as it does for a tie now.
- A load region never uses a face of its support region.
- A described case with more than 4 candidates gives `unknown`, and the reason gives the count. The limit keeps a job inside its 600 s budget. Step 1 measured it (see What it decides). It applies only to described cases, because the reviewed `largest_flat` rule already gives 6 candidates on a cube.
- The 1% bands, the 1° tolerance and the disc fraction are constants in the check. The agent cannot change them.
- A hole support keeps its keep-out of 0.5 × the bore. An inner-curve support gets the same keep-out, 0.5 × its diameter. Every flat support, `EndOf` and `Facing` included, carries the clamped-face note.
- A region is a set of BREP faces, and it takes the mesh triangles on those faces by gmsh surface tag. Step 1 measured that gmsh keeps one tag per BREP face, in the kernel's order, on all 24 parts it read (§2.1 of the phase 3 design). The check does not rest on that order alone: when the mesh and the kernel count different faces, or a tagged triangle lies off the surface the kernel reads on its face, the result is unknown. A middle disc also keeps only the triangles wholly inside it.

## How each property holds

**Frame-free.** Every term reads normals, principal axes, centroids, areas, hole axes and openings. None reads a coordinate, the bounding box or the order of faces. A harness case turns and moves each test part and checks that the same faces come back.

**Written before any stress result of the brief exists.** The result rule in `propose_requirements` refuses a described load case whose `unit_case` no earlier proposal of the brief carried, once any variant of the brief has a stored `fea` result, whatever its verdict. Before any such result exists, the agent may replace a description, because it has seen no result to choose between. A later proposal may carry an earlier described case with a new force, because the force is the person's number and `unit_case` leaves it out. The agent picks the terms knowing the shape, as it does when it picks a reviewed phrase, and variants may already exist. It never picks them knowing a stress result of that brief. The rule makes sure that no `fea` result of the brief exists when the case is written, and that no other case can be written once one does. It is looser than the blind rule for agent-written checks on purpose. A rule of "before any variant" would send the common path, a load stated after the options are built, back to the five reviewed phrases.

**The person confirms plain words.** The server writes the words from the terms. The agent supplies no words for a load case. A harness case lists every pairing of terms and checks that no two share words and that none shares words with a reviewed phrase. The page marks the row as the agent's description.

**Ties go to the worst case.** Every term gives candidates, such as each face in a tie within its band, each match of `Each`, each face of `InOneFlatFace` and each face of a facing pair. The check solves them all and keeps the worst. Adding a matching hole or curve adds a candidate, so it cannot raise a result under `Each` or `InOneFlatFace`. Adding a third hole to a face under `InOneFlatFace(2)` gives `unknown`, never a pass. `OnLargestFlat` and `OnFarthest` pick by size and distance, so a new larger or farther face moves the load. That gap is listed below.

**Fails closed.** Each term's `unknown` case is in the table above. The reason names the term and what it found, such as "no flat face faces another across a gap". Auto treats `unknown` as not passing.

**No change after a result.** The described case is part of the requirement and of its load case id, and the person's Confirm pins it in the signed decision. The result rule refuses a new case once the brief has a `fea` result. It also refuses a proposal that leaves out a described case once that result exists, unless the person declined a proposal since. So the agent cannot propose two readings, see which scores better and keep that one. No tool edits a load case.

## What the page, scorecard and tracer show

| | Reviewed phrase | Described load case |
|---|---|---|
| Confirmation page | the words | the words, and "The agent described where this part is held and loaded. Confirm only if these words match how it will be used." |
| `Checked` and `Waiting` rows | as now | `load_case: "described"` |
| The agent's report | "passes" | "passes on a load case I described", with its words |
| `fea` result | as now | as now. The formula text names the terms and their rules |
| Auto stop | counts toward every requirement passing | counts too, and the stop report names it |
| Tracer | the measure resolves through `CheckStep`, the limit through `ConfirmedStep` | the same, plus a basis rule that `load_case` matches the confirmed load case, and a separate count that never enters the headline count |

`load_case` sits beside `basis`. A row can rest on a researched value and on a described load case at once. Step 3 adds, for every load case, the faces of the deciding candidate's support and load to the `fea` result, and the 3D view highlights them. The person sees where the check held and loaded each variant without picking anything.

## Harness cases before it ships

1. `tests/checks/test_anchors.py`, with fake faces: each term's candidates, the 1% band, every `unknown` case in the table, the candidate limit, and a load term that would use a support face.
2. Parse and words: each refused pairing, and a test that enumerates every pairing of terms and directions and finds no two with the same words, and none with a reviewed phrase's words.
3. `tests/checks/test_anchors_in_image.py`: the hook, a two-curl rail hook, a clamp, a shelf, `sb_arm` and `sb_l_bracket` resolve to the same faces under the existing rotations and moves.
4. `tests/fea/cases.py`, with each bound measured first, as §2.9 of the phase 3 design did:
   - A plate fixed at one flat end and pressed into the middle of its largest flat face, `FlatEnd`, `OnLargestFlat(middle)` and `Into`. Built against the tip deflection of a cantilever loaded at half its length, on a 160 × 40 × 2.5 plate, measured +0.13% on the fine mesh. The plate is thin so that the disc is about 3.5 coarse elements in radius. On a 6 mm plate the disc was 1.6 elements in radius, and the triangles wholly inside it covered 70% of it in the arm64 image and 48% in CI's amd64 image, where gmsh builds a different mesh. So a press on the middle decides only when the disc is a few elements wide, and near that edge the answer can differ between machines. Sizing the mesh to the disc would remove the edge. That is not built. A first version held a 52 × 50 plate across its middle axis and read the root stress. It was 18.5% over the beam value, because a wide, short plate carries more of the moment under the load than a beam does, so it proved little. Host tests cover `EndOf(middle)`.
   - A bar with two equal holes, `Each(HOLE)` and `OnFarthest(HOLE)`, across the hole axis. Both candidates give the same result, and it matches beam theory outside the keep-out.
   - A C-frame clamp, `Facing`, `OnOpposite` and `Into`. Built against the jaw tip's displacement by Castigliano, not M/Z + F/A: the stress at the back of the C peaks at re-entrant corners and at the clamped jaw, where it depends on the mesh.
   - A J hook, a shank held by 2 holes with a half ring below it, `OnFarthest(INNER_CURVE)` and `Away`. The expected value is the Winkler-Bach curved-beam stress at the curl's root.
   - An L bracket with 2 holes in each leg, `InOneFlatFace(2)`. The result equals the worse of the two single-face solves.
5. Proposals: on a brief with variants and no `fea` result, a new described case is accepted and may replace an earlier one. Once any variant has a `fea` result, `unknown` included, a new described case is refused, the same `unit_case` with a new force is accepted, and a proposal that leaves one out is refused unless the person declined since.
6. Scorecard and tracer: a verdict on a described case carries the label, the tracer fails a card whose label does not match its confirmed load case, and the summary counts described verdicts apart.
7. A live walk through the MCP server: a fresh brief for a wall hook is built with no load. The person then states a load, and a described case for it is accepted while no stress result of the brief exists. It is confirmed and scored, and its verdict carries the label. The same load described with other terms after that result exists gets the refusal, and the agent uses a reviewed phrase.

## What changes version

- Every check's version. `check_version` hashes each check's own file and every shared file of the container package (read), and `anchors.py` and `wire.py` are shared. Every stored result goes stale and is scored again.
- The load and requirement models gain kinds, and the scorecard gains `load_case`, so the API types are generated again. Stored load cases keep their wire form and their ids.
- The guidance gains a paragraph on load cases, and `DEEPER_ANALYSIS` says that a load stated on built variants may use the terms until the brief has a `fea` result, and a reviewed phrase after.
- Inferred to stay the same: the materials table, the analysis image's libraries, and the TLA+ protocol models. The refusal is a check inside `propose_requirements`. Neither the job queue nor the confirmation answer flow changes.

## What it does not cover

- Supports that rest, slide or pivot, such as a shelf on brackets or a lid on a box. Every support is fixed. Fixing a part that only rests makes it stiffer than it is, and its mid-span stress lower, so the list has no "rests on" and such briefs stay unverified. They are their own piece of work ([#254](https://github.com/laminarityai/cad/issues/254)).
- A load given as a displacement (a snap arm bent 2 mm), a torque, self-weight, or two loads that act together.
- Contact with another part, threads, bolt preload and bearing at a hole.
- Inner curves that are not circular cylinders, such as a torus fillet. The kernel reports such a face as `Curved`, with no concavity, so it never matches.
- Edges and points as regions.
- A new description after the brief has a `fea` result. Only the reviewed phrases serve a load stated then. A described case that the person declines after that result cannot be replaced on that brief either.
- Geometry shaped to a description after it is frozen, such as a larger flat face added so that `OnLargestFlat` moves. No gate tells this from honest design. The words, the highlighted faces of step 3 and the label are the defence.
- The large-displacement gate and the node cap.

## Build order

Each step is one PR, after option A merges.

1. **One resolver, and the terms.** Built on branch `feat/fea-described-load-terms`. In the container only. First move the five phrases' rules into one function that returns candidates for any term, with no change to their results. Check that by scoring the corpus before and after. Then add the seven terms, `middle`, `Into`, `Away`, the candidate limit and the kernel query that tells whether a point is inside the solid. Measure whether gmsh keeps a surface tag per BREP face, and use the tags if it does. Harness cases 1, 3 and 4. Measure the candidate limit, the middle disc and the bands. Report what the terms cover, measured on the corpus and the novice briefs, so the operator can decide on agent-written code that picks the faces. Every check version moves. Nothing can propose a described case yet.
2. **Proposals, page, card and tracer.** The models and wire, `describe_case` and the words test, the parse rules, the result rule in `propose_requirements`, the page note, `load_case` on `Checked` and `Waiting`, the line in the Auto stop report, the tracer rule and count, and the guidance. Pointers in §2.1 of the phase 3 design and in the recommendation of fea load anchors. Harness cases 2, 5, 6 and 7. Report how often an honest description is stuck because an `unknown` `fea` result counts as a result.
3. **Show where.** The `fea` result names the faces of the deciding candidate's support and load, and the 3D view highlights them on the card, for reviewed phrases too.

### Build step 2, as built

Built on branch `feat/fea-described-load-proposals`. Where it differs from the text above or settles what it left open:

- **Where the rule lives.** `briefs/described.py` holds the pure rule (`check_proposed`). `variant_sets/stressed.py` reads the stored results, because `variant_sets` sits above `briefs` and `checks` in the import layers. `propose_requirements` calls both.
- **The result rule reads every revision of every slot.** Any stored signed `fea` job result of the brief's variant set counts, whatever its verdict. A variant built outside the set and scored with the brief's `brief_id` is not seen. That gap is left open.
- **Assumptions refuse a described case.** `assume()` raises for one. An assumption takes an agent-supplied force, and the measure-only result it runs would lock the brief. The note did not say this.
- **An assumed or awaiting reviewed-phrase load also creates a stored `fea` result.** So it closes the window for a later described case. See the stuck report below.
- **The `hole_axis` direction rule applies to described cases only.** A reviewed case stored before the rule still reads.
- **The label.** `Checked` and `Waiting` carry `load_case: "described"`, set by `scorecard.requirements.labelled`. Auto adds `Standing.described` and `AllPass.described` beside `agent_checked`, and does not add a `Mark`, because a described row can also be researched.
- **The tracer.** `By.DESCRIBED` sits outside the reviewed count and takes precedence over researched. `evals/briefs/confirmation.py` fails a card whose label differs from its confirmed load case, in either direction.
- **The page and the card.** A described row carries `note` (the sentence in the table above). The page and the chat Confirm card both show it. The scorecard row shows the label, keeps the full words in its expanded panel, and the card summary counts described passes apart.
- **Versions.** Every `fea` result went stale, as expected, because `wire.py` and `terms.py` changed. The protocol models are unchanged. No covered file was touched.
- **Not built.** Highlighting faces (step 3).

**How often an honest description is stuck.** Not measured. No corpus of briefs with their stored results exists in the repo (the 19 parts of the load anchors note were not kept), and a number needs real conversations. Two things are known. First, any stored `fea` result closes the window, including a measure-only result of an assumed or awaiting reviewed-phrase load that came out `unknown` (a hook resolves to `unknown` under the reviewed phrases). Second, the live walk saw a result close the window early: the first revision scored the described load as `unknown` within the check's stated error, and from then on only that description, or the same one with a new force, was allowed. To measure it, take the stored `fea` results of finished Auto and chat runs, and count the briefs where the first result is `unknown`, or is measure-only, and a later proposal described a load that the refusal rejected. Report the count over all briefs with a stated load.

Each of these needs its own evidence and issue: supports that rest ([#254](https://github.com/laminarityai/cad/issues/254)), displacement loads, and a describer that sees only the person's words.

## What it decides

Measured in build step 1, in the analysis image, with PLA (E 2300 MPa, ν 0.34, yield 51 MPa), 20 N and a 2 mm deflection limit, as the corpus baseline uses. "Decides" means the `fea` check gives `pass` or `fail`, not `unknown`.

**The reviewed phrases, before and after.** The corpus of 19 parts and `i_beam_flat` scored the same on origin/main, after the one resolver, and after selection by surface tag: the same verdict, requirement verdict, every measure and the same reason on all 20. 8 parts stop at the large-displacement gate: `cantilever_bar`, `l_plain`, `l_holes`, `l_filleted`, `hook`, `t_arm`, `t_arm_flat_end` and `truss_arm`. 4 stop on their anchor: `equal_angle` and `sb_gusset` (no flat end), `sb_arm` (2 holes of 28 mm, 1 named) and `sb_l_bracket` (4 holes of 5.1 mm, 2 named). So 12 of 20 are stuck, not the 4 an earlier count gave.

| Part or brief | Terms | Candidates | Result |
|---|---|---|---|
| `hook` | `Holes(2, 4 mm)`, `OnFarthest(INNER_CURVE)`, across the hole axis | 1 | Decides. `pass`, 2.87 mm, safety factor 2.97, so the 2 mm requirement fails. The reviewed far end gives 3.56 mm and stops at the 5% gate. |
| `sb_l_bracket` | `InOneFlatFace(2, 5.1 mm)`, far end, any way | 2 | Decides. `pass`, 1.76 mm, safety factor 4.35, so the 2 mm requirement passes. |
| `sb_arm` | `Each(HOLE, 28 mm)`, `OnFarthest(HOLE, 28 mm)`, across the hole axis | 2 | Resolves, not solved. A pin is a pivot, which stays not checked (decision 9). |
| `equal_angle` | none | | Not decided. `EndOf(middle)` finds no flat end. `EndOf(short)` finds the two cut ends of the L profile, which is not "one leg fixed". |
| `sb_gusset` | none | | Not decided. `EndOf(middle)` finds the long edge face of the triangle, which is not "one end". |
| The 7 other parts at the gate | any | | Not decided. The gate reads the displacement, and no load term changes it. |
| A shelf pressed in the middle, screwed through its back (120 × 200 × 6 plate on a flange with 3 holes of 5 mm) | `Holes(3, 5 mm)` or `InOneFlatFace(3, 5 mm)`, `OnLargestFlat(middle)`, `Into` | 1 | Decides. `pass`, 0.98 mm, safety factor 22.4. |
| A hook hung from a rail (an S hook with curls of 16 mm and 20 mm bore) | `Each(INNER_CURVE)`, `OnFarthest(INNER_CURVE)`, `Away` | 2 | Decides. `pass`, 0.46 mm, safety factor 10.8. The curl on the rail is fixed, though a curl hooked on a rail rests on it. Whether decision 9 covers it is the operator's call. |
| A clamp (a 60 × 20 × 50 block with a 20 mm slot cut in from one side) | `Facing`, `OnOpposite`, `Into` | 2 | Decides. `pass`, 0.31 mm, safety factor 14.5. With `OnOpposite(middle)` it is `unknown`: the disc on a 20 mm jaw is 3.2 mm across and the coarse mesh covers 24% of it. |
| A bracket bolted to a wall through a face | `InOneFlatFace(n, d)`, far end | | As `sb_l_bracket`. |
| A lid pushed down | none | | Not covered, because it rests on the box. |
| A snap arm bent at its tip | none | | Not covered, because the load is a displacement. |
| A plate fixed at one end, pressed in the middle (160 × 40 × 6) | `FlatEnd`, `OnLargestFlat(middle)`, `Into` | 4 | Decides. `pass`, 4.98 mm, safety factor 7.4. `EndOf(middle)` would fix a long side, because the middle axis of a long plate runs across it. |

Of the 12 stuck corpus parts, the terms decide 2, `hook` and `sb_l_bracket`. Of the 6 novice briefs, they decide 3 (the shelf, the clamp and the bracket), or 4 if a hooked curl counts as fixed. What the rest need:

- `equal_angle` needs a support on one leg's face. No term names a leg. Agent-written code that picks the faces would, or a term for "the face of a leg".
- `sb_gusset` needs the person to say which edge is held. A triangle has no ends a rule can find.
- `sb_arm`, the lid and a rail hook that rests need supports that pivot or rest ([#254](https://github.com/laminarityai/cad/issues/254)).
- The 7 parts at the gate need a geometrically nonlinear analysis, or a smaller force.
- The snap arm needs a displacement load.

**Candidate limit.** Measured counts: the reviewed phrases give 1 to 4 candidates on the corpus (4 on `square_tab`), and the described cases give 1 to 4 (4 on the plate). The limit of 4 never stopped a case. On the described parts, meshing and solving took about 3 to 100 s per candidate (`sb_l_bracket` took 203 s for 2). A whole reviewed score took up to 227 s for 1 candidate (`i_beam_arm`) and 451 s for 2 (`i_beam_flat`). So 4 candidates fit the 600 s budget at up to about 150 s each. At the rate of the 2 heaviest corpus parts, even 3 would not fit. It is inferred that the job's time limit then gives `unknown`, and that the limit should stay at 4, since a higher one would only add jobs that time out.

**The middle disc.** The coarse and fine meshes covered 67% and 77% of the disc on the shelf, 67% to 70% on the plate, and 23% to 55% on the clamp's jaws. The disc's radius is 15.5 mm on the shelf, 8 mm on the plate and 3.2 mm on the jaw, against coarse mesh sizes of 5.6, 5.1 and 3 mm. It is inferred from these 3 parts that a disc whose radius is under about 1.5 coarse elements gives `unknown`. It is inferred that a floor on the radius, such as 2 coarse elements, would decide the clamp. That floor is not built, because it ties the load's size to the mesh.

**Bands.** No measured part had a candidate near a band. Every tie was an exact one, by symmetry. The next largest flat face was 95% of the largest on the shelf and 15% on the plate. No `OnFarthest` case had a second match outside the support. The clamp's jaws face within 0° of opposite. The line for `Away` was 61% of the part's reach on the hook and 80% on the rail hook, against the 1% floor. So the 1% bands and the 1° tolerance are not contradicted, and these parts do not test them.

## What the operator decided, and what build measures

The operator approved route 4 on 2026-11-11. Items 2, 3, 4 and 8 were approved as written. Items 1, 9 and 10 record the operator's decisions. Items 5, 6 and 7 are constants that build step 1 measures.

1. **A load stated after variants exist, and a declined description.** The operator chose the result rule, which differs from the draft's pick. The draft refused a new described case once the brief had a variant. The result rule refuses one only once any variant of the brief has a stored `fea` result, and before that the agent may replace a description. A rule of "before any variant" would send the common path back to the five reviewed phrases. The cost is that the agent picks the terms knowing the shape, as it does for a reviewed phrase. It never picks them knowing a stress result of that brief. One question is not settled. It is whether a `fea` result that is `unknown` because a term found no match counts as a result. This note takes the strict reading, and build step 2 reports how often an honest description is stuck by it.
2. **Leaving out a described case.** Approved as written. The pick is to refuse it unless the person declined since. Without the rule, the agent could propose two readings and keep the one that scored better.
3. **Labelled and counted apart.** Approved as written. The pick is yes, with no place in the headline count. Treating it as reviewed would make a pairing nobody reviewed read like a team phrase.
4. **Auto.** Approved as written. The pick is that a pass on a described case counts toward the stop when every requirement passes. If it did not count, Auto would never stop on a pass for these briefs.
5. **Candidate limit.** A constant that build step 1 measures, starting from 4. A higher limit risks the 600 s budget. Measured: it stays 4. No measured case went over it, and the plate reached it (What it decides).
6. **The middle disc.** A constant that build step 1 measures, starting from a radius of 0.1 × √(face area), like the keep-out. A stated contact size would be a number the person must give. Searching for the worst position on the face would move the load away from where the person said it acts. Measured: the radius stays 0.1 × √(face area). The disc decides on the shelf and the plate and gives `unknown` on a small jaw (What it decides).
7. **Bands and tolerances.** Constants that build step 1 measures, starting from 1% for ties, as `LONG_TIE_FRACTION` is now, and 1° for facing faces. Measured: they stay. No measured part came near them (What it decides).
8. **The page note.** Approved as written. The pick is two sentences on a described row. Without it the person may not see that the agent wrote the description.
9. **Supports that rest.** The operator decided that supports that rest, slide or pivot stay unverified. They are their own piece of work ([#254](https://github.com/laminarityai/cad/issues/254)). Treating them as fixed would give a pass the part may not earn.
10. **How big the list is.** The operator approved the terms now, four supports and three loads, each tied to a brief. Agent-written code that picks the faces (route 3) is deferred, not rejected. The operator decides on it after build step 1 reports what the terms cover, measured on the corpus and the novice briefs. A nested grammar would cover more, at the cost of words that grow long and are hard to keep distinct.
