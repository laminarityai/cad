# Context parts and the fit check

SPEC says a context part is a part the new part must fit with. A person attaches one to the project, or an earlier variant becomes one, and confirms it on the one confirmation page before a check measures against it. The fit check then measures each variant against every confirmed context part of its project, and reports the overlap volume and the minimum clearance. Issue #92 holds the prototype that settles how the check measures. Reading parts from Onshape or Fusion (#60) is out of scope.

## Usage

The agent's side, through MCP:

```
create_brief("A clip that slides onto the rail from variant 3f.., 0.2 mm clearance on every side")
propose_context_part(brief_id, quote="the rail from variant 3f..", name="rail", variant_id="3f..")
  -> {part_id: "part-9c1e..", status: "waiting", box: {min: [..], max: [..]}, volume_mm3, solids}
propose_requirements(brief_id, [{kind: "min_clearance", part: "part-9c1e..", clearance: 0.2 mm, quote: ".."}])
ask_to_confirm(project_id)            # one page: the requirements and the rail
  -> items: [{kind: "requirements", ..}, {kind: "context_part", part_id, outcome: "confirmed", box}]
build_variant(code built in the rail's frame, brief_id)
score_variant(variant_id, material_key, brief_id)
  -> results: [.., {check_id: "fit", instance: "part-9c1e..", verdict, measured: overlap_volume, min_clearance}]
  -> basis.requirements: [{statement: "At least 0.2 mm clear of rail", check_id: "fit", verdict}]
```

The person's side: the page shows a section "A part your design must fit with". Its row gives the name, the words of the brief it came from, where it came from (variant id), its bounding box and volume, and what decides against it ("The fit check fails a variant that overlaps it and measures the clearance between them"). Confirming the page confirms the part.

## Data shape

A context part is a signed record in the project store. Its geometry is a content-addressed BREP beside it. Status is never stored. It is derived from the page answers, as for requirements (ADR-0004).

```python
# src/cad/context_parts/model.py
ContextPartId = NewType("ContextPartId", str)  # "part-" + brep_sha256[:16]


class FromVariant(_Frozen):
    kind: Literal["variant"] = "variant"
    variant_id: str  # 16 hex


type PartOrigin = Annotated[FromVariant, Field(discriminator="kind")]
# Later arms, one per path: FromUpload(file_name, step_sha256), then Onshape and Fusion (#60).


class Facts(_Frozen):
    """Measured by the analysis container at ingest. Shown to the person and the agent so they can
    recognise the part and build in its frame. No check reads them."""

    solids: int
    volume_mm3: float
    box_min: tuple[float, float, float]
    box_max: tuple[float, float, float]


class ContextPartRecord(_Frozen):
    project: ProjectId
    brief_id: BriefId
    name: str  # 1..80 chars
    origin: BriefSpan  # the brief words it came from
    source: PartOrigin
    brep_sha256: str
    facts: Facts
    proposed_at: datetime

    @property
    def id(self) -> ContextPartId: ...
```

On disk, under the projects root that the projects key signs (ADR-0003):

```
~/.cad/projects/<project_id>/context_parts/0001.signed   slot "<project_id>/context_part/<n>"
~/.cad/projects/<project_id>/parts/<brep_sha256>.brep    read back only when its SHA-256 matches
```

```python
# src/cad/context_parts/store.py
def propose(roots, variants_root, brief_id, quote, name, variant_id) -> Stored
    """Idempotent: the same BREP in the same project returns the stored record that is still
    waiting or confirmed. A part declined before gets a new record."""
def stored_parts(projects, project) -> tuple[Stored, ...]        # Stored(number, record, ref)
def confirmed_parts(projects, project) -> tuple[ConfirmedPart, ...]  # newest record per id, confirmed
def part_brep(projects, project, part: ConfirmedPart) -> bytes   # raises TamperedProject on a hash mismatch
```

`Stored.ref` is the `ItemRef(kind="context_part", slot, sha256)` of the record, so the page answer ledger (`confirmations.answers.Ledger.of`) answers "confirmed, declined or waiting" with no new state.

## Ingest

The variant's BREP is agent-made geometry, so it is read only inside the analysis container. A small container entry, `cad.checks.container.ingest`, reads the BREP from stdin with the same kernel the checks use and reports `Facts`, or a reason it cannot be a context part: no solid, sub-shapes outside its solids, a solid that fails `BRepCheck`, or a tolerance over 1e-3 mm (#92). A refused part is never stored. The host side is `cad.context_parts.ingest.ingest(brep) -> Facts | NotAPart`.

## Confirmation item

`ItemKindName` becomes `Literal["requirements", "context_part"]`. `cad.confirmations.context_parts.ContextParts` implements `ItemKind`. `pending` lists each stored record that no page answer names. `section` returns one row per record. `edit` refuses every edit, because a part has no number to change. `registry.kinds` adds it. `ask_to_confirm` reports each context part with its id, outcome and box.

## Fit check

`src/cad/checks/container/fit.py` is a background check, one job per confirmed context part, as `fea` is one job per load case. Its `instance` is the part id.

- `REQUIRES = (interference,)`. A variant whose own solids overlap makes Common wrong (#92).
- Preconditions give `unknown` with a reason: no context shape, either side has sub-shapes outside its solids, a solid fails `BRepCheck`, or a tolerance is over 1e-3 mm.
- Overlap first: `BRepAlgoAPI_Common` per pair of solids, default settings. `overlap_volume` is the sum in mm^3.
- Clearance only when the overlap is at most 0.001 mm^3 (the interference threshold). Otherwise `min_clearance` is 0 and the distance is skipped, which is right for nested parts. The distance is `BRepExtrema_DistShapeShape` with `Extrema_ExtFlag_MIN`, single-threaded, per pair, rounded to 1e-6 mm, with under 1e-7 read as 0.
- Verdict: `fail` when the overlap is over 0.001 mm^3, `pass` when both measures exist, `unknown` otherwise. Confirming a context part is confirming that the new part must not overlap it, and the page row says so.
- Budget: `Background(wall_seconds=60, memory_mb=2048, tmpfs_mb=...)`. A distance that runs past the wall makes the whole job `unknown` ("did not finish within 60 s"). Keeping the overlap from a killed job is a follow-up.

The container receives the context BREP after the variant BREP on stdin. `RequestWire` gains `context_bytes: int`, the length of the tail, and `Subject` gains `context: Shape | Unreadable | None`. `Kernel` gains `min_distance(a, b) -> float | None` and `max_tolerance(shape) -> float`.

On the host, `jobs.Demand` becomes a typed pair, so a load case is never paired with the fit check:

```python
@dataclass(frozen=True, slots=True)
class Demand:
    loads: Mapping[str, LoadCaseWire] = {}  # fea instances
    parts: Mapping[ContextPartId, PartBrep] = {}  # fit instances; PartBrep(sha256, data)
```

`JobSpec` gains `context: PartBrep | None`, and its `key` hashes the context SHA-256, so a new part never reuses a cached result. `score_variant` with a `brief_id` adds the confirmed context parts of the brief's project. Without a brief, no fit runs.

## Requirement kinds

Two kinds, the way `min_mass` and `max_mass` pair:

```python
class MinClearance(_Frozen):  # "at least 0.2 mm clear of the rail"
    kind: Literal[Kind.MIN_CLEARANCE]
    part: ContextPartId
    clearance: Length


class MaxClearance(_Frozen):  # "no more than 0.5 mm gap to the rail"
    kind: Literal[Kind.MAX_CLEARANCE]
    part: ContextPartId
    clearance: Length
```

`deciding_check` gives `fit`. `limits` gives `min_clearance` at least or at most the clearance. The instance a requirement reads is its `part`, as a load requirement reads its load id. `propose_requirements` refuses a part id the project does not store. A requirement whose part is not confirmed is judged `unknown` with the reason "the context part is not confirmed", never an error. A min clearance is the only thing a person needs to say for a slide-on fit. A max clearance stops a part that passes by sitting far away from the context part.

## Tracing

A fit measure resolves under the tracer's existing rule, because a registered check computed it. The tracer adds one rule: a `fit` result's instance must name a context part that the person confirmed in the card's project, with a BREP whose SHA-256 starts with the id's 16 digits. Otherwise the card fails.

## Rejected shapes

- **A context part is a variant id.** Variant ids re-derive from code and the image tag (ADR-0003), so every image change would make the confirmed part stale and ask the person again. An upload has no code. The variant store is also global, and a context part belongs to a project.
- **Fit in the quick job, every part in one container.** The distance can run past 60 s on a real part (#92). That would turn every quick check unknown.
- **A `measure_limit` bound to `fit:min_clearance`.** It cannot say which context part. Adding an instance field to every bindable measure would leak a fit detail into a general kind.
- **A no-overlap requirement kind.** Nothing a person says needs it. Confirming the part already says the new part must fit with it. A press fit, which overlaps on purpose, is out of scope.

## Delivery

1. Context part store, ingest, the page item, and `propose_context_part`. Proof: the page shows a context part.
2. The fit check, the demand, the two requirement kinds and the tracer rule. Proof: a scorecard with fit results and a clearance verdict.
3. Upload. The person picks a STEP file on the page. It needs a STEP reader in ingest, a multipart body on the page, and a `FromUpload` origin.
