from typing import Annotated, Final

from pydantic import BaseModel, Field

from cad.auto.gate import gate, stops_at_the_limit
from cad.briefs import store as briefs
from cad.context_parts.model import UPDATE_PART
from cad.context_parts.store import out_of_date_in
from cad.conversations.model import Mode, ModeRefused
from cad.operations.model import Audience, Input, Tenant, operation
from cad.operations.research import brief_table
from cad.operations.scorecards import MaterialKey
from cad.sandbox import container, host, image
from cad.scorecard import material
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import (
    MAX_MEMBERS,
    Differs,
    Joined,
    Label,
    MaterialChoice,
    Option,
    Reason,
    Resolve,
    SetBuildResult,
    SetRefused,
    SlotRefused,
)
from cad.variant_sets.placement import choose
from cad.variants import entry, store

MAX_CODE_CHARS: Final = 256 * 1024
BUILD_VARIANT = (
    "Build one variant from build123d Python code in a sandbox with no network, "
    f"{container.MEMORY_MB // 1024} GB of memory and a {container.WALL_SECONDS} second limit. "
    f"The code runs as a script; {host.CONTRACT}. "
    "Returns the variant id, the outcome (built, build_failed with the error and traceback, "
    "timed_out, out_of_memory or no_result) and the tail of what the code printed. "
    "Building the same code again returns its stored outcome without rebuilding, "
    "except after a timeout. "
    "Pass brief_id once the user has confirmed the brief's requirements: a built variant then "
    f"joins the brief's variant set, which holds up to {MAX_MEMBERS} variants for the user to "
    "compare, and variant_set names its slot and revision. A new set gets 2 or 3 options, each "
    "in its own slot, that differ in a way the person would choose between, not in small "
    "dimensions. Give each a label of a few words and differs, one line saying how it differs "
    "from the others. On a revision, omit both to keep the slot's label, or pass both to change "
    "them. A part that must fit another part is modelled in that other part's frame, its origin "
    "and axes, so the fit check and the page show them together. To change a variant the user "
    "asked about, such as making a wall thicker, "
    f"build the edited code with brief_id and that variant's slot, 1 to {MAX_MEMBERS}: it becomes "
    "the slot's next revision, and the set shows it in place of the old one, which stays in the "
    "slot's history. The person never chooses the material. When a confirmed made_of "
    "requirement names it, the slot uses that material and you pass none. Otherwise you choose "
    "it for each variant, and variants may differ: pass material_key, a key from list_materials "
    "or one of your own for a material the table lacks, which you then research, and "
    "material_reason, one line saying why this material suits this variant. The server records "
    "the choice with the slot's revision, the person's page shows it as chosen by the agent, "
    "and it is a design choice, not a requirement and not a verdict. Omit both to keep the "
    "slot's earlier choice; a new material with the same code is a new revision. A build with "
    "no confirmed made_of, no earlier choice for the slot and no material_key is refused before "
    "it starts. A built variant has no verdicts until you score it: call score_variant "
    "with its variant_id and the brief_id, and the person's scorecard shows pending until you "
    "do. "
    "Without slot, code already shown in a slot keeps that slot, and new code "
    "takes the lowest free slot. A build for a brief with no confirmed requirements, for new "
    "code with no slot when every slot is taken, or for code that another slot already shows, "
    "is refused before it starts. If the set changes while a build runs so that it cannot take "
    "the code, the build finishes and is stored, but the error says it joined no set and names "
    "its variant id. Without brief_id the variant joins no set, and slot is refused. "
    "In Plan mode the build is refused: the person switches the conversation to Design or Auto "
    "mode in the web app. Under an Auto run, which the conversation holds, pass the run's "
    "brief_id: the build is refused before it starts once the run has stopped, and a build of "
    "code the store does not hold is charged to the account's usage limit, whose refusal stops "
    "the run. context_parts_out_of_date names the confirmed context parts that came from an "
    "earlier revision of the slot this build joined: " + UPDATE_PART
)


VARIANT_CODE = (
    "The build123d code a stored variant was built from. To change a slot the user names, read "
    "the slot's variant_id from variant_set, read its code here, edit it, and build the edited "
    "code with build_variant, the brief_id and that slot, then score the new variant with "
    "score_variant."
)


class VariantCodeInput(Input):
    variant_id: str


class VariantCode(BaseModel):
    variant_id: str
    code: str


def variant_code(tenant: Tenant, arguments: VariantCodeInput) -> VariantCode:
    held = entry.open_entry(tenant.variants, arguments.variant_id, image.image_tag(image.BUILD))
    code = (held.directory / entry.CODE).read_bytes().decode("utf-8", "surrogatepass")
    return VariantCode(variant_id=held.id, code=code)


class BuildVariantInput(Input):
    code: Annotated[str, Field(max_length=MAX_CODE_CHARS)]
    brief_id: str | None = None
    slot: Annotated[int | None, Field(strict=True)] = None
    material_key: MaterialKey | None = None
    material_reason: Reason | None = None
    label: Label | None = None
    differs: Differs | None = None


def _option(label: str | None, differs: str | None) -> Option | None:
    if label is None and differs is None:
        return None
    if label is None or differs is None:
        raise SetRefused(
            "label and differs go together: pass both to name the option, or neither to keep the "
            "slot's. Nothing was built."
        )
    return Option(label=label, differs=differs)


def chooser(tenant: Tenant, brief_id: str, key: str | None, reason: str | None) -> Resolve:
    """The material a build in the brief's set records: the person's made_of, else the agent's."""

    def resolve(previous: MaterialChoice | None) -> MaterialChoice | None:
        table = brief_table(tenant.roots, brief_id).table
        pinned = material.pinned_key(briefs.confirmed_requirements(tenant.roots, brief_id), table)
        return choose(pinned, previous, key, reason, table)

    return resolve


def build_variant(tenant: Tenant, arguments: BuildVariantInput) -> SetBuildResult:
    if tenant.mode is Mode.PLAN:
        raise ModeRefused(
            "build_variant is refused in Plan mode: the person switches this conversation to "
            "Design or Auto mode in the web app"
        )
    running = gate(tenant, arguments.brief_id)
    if running is not None and arguments.brief_id is not None and arguments.slot is not None:
        variant_sets.refuse_a_slot_out_of_turn(tenant.roots, arguments.brief_id, arguments.slot)
    option = _option(arguments.label, arguments.differs)
    vid = entry.variant_id(arguments.code, image.image_tag(image.BUILD))
    with stops_at_the_limit(tenant, vid):
        if arguments.brief_id is not None:
            resolve = chooser(
                tenant, arguments.brief_id, arguments.material_key, arguments.material_reason
            )
            built = variant_sets.build_into_set(
                tenant.roots,
                tenant.variants,
                arguments.brief_id,
                arguments.code,
                arguments.slot,
                resolve,
                option,
            )
            return with_out_of_date(tenant, arguments.brief_id, built)
        if arguments.slot is not None:
            raise SlotRefused("slot names a place in a brief's variant set, so pass brief_id too")
        if arguments.material_key is not None or arguments.material_reason is not None:
            raise SetRefused(
                "material_key and material_reason record a choice in a brief's variant set, "
                "so pass brief_id too"
            )
        if option is not None:
            raise SetRefused(
                "label and differs name a slot of a brief's variant set, so pass brief_id too"
            )
        built = store.build_variant(arguments.code, tenant.variants)
    return SetBuildResult(variant_id=built.variant_id, outcome=built.outcome, output=built.output)


def with_out_of_date(tenant: Tenant, brief_id: str, built: SetBuildResult) -> SetBuildResult:
    joined = built.variant_set
    if not isinstance(joined, Joined):
        return built
    project = briefs.read_brief(tenant.roots, brief_id).project
    stale = out_of_date_in(tenant.roots.projects, project, brief_id, joined.slot)
    return built.model_copy(update={"context_parts_out_of_date": stale})


OPERATIONS: Final = (
    operation(
        name="build_variant",
        audience=Audience.AGENT,
        description=BUILD_VARIANT,
        input=BuildVariantInput,
        output=SetBuildResult,
        run=build_variant,
    ),
    operation(
        name="variant_code",
        audience=Audience.AGENT,
        description=VARIANT_CODE,
        input=VariantCodeInput,
        output=VariantCode,
        run=variant_code,
    ),
)
