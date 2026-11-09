from typing import Annotated, Final

from pydantic import Field

from cad.operations.model import Audience, Input, Tenant, operation
from cad.sandbox import container, host
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import MAX_MEMBERS, SetBuildResult, SlotRefused
from cad.variants import store

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
    "compare, and variant_set names its slot and revision. Build 3 to 5 different variants, each "
    "in its own slot. To change a variant the user asked about, such as making a wall thicker, "
    f"build the edited code with brief_id and that variant's slot, 1 to {MAX_MEMBERS}: it becomes "
    "the slot's next revision, and the set shows it in place of the old one, which stays in the "
    "slot's history. Without slot, code already shown in a slot keeps that slot, and new code "
    "takes the lowest free slot. A build for a brief with no confirmed requirements, for new "
    "code with no slot when every slot is taken, or for code that another slot already shows, "
    "is refused before it starts. If the set changes while a build runs so that it cannot take "
    "the code, the build finishes and is stored, but the error says it joined no set and names "
    "its variant id. Without brief_id the variant joins no set, and slot is refused."
)


class BuildVariantInput(Input):
    code: Annotated[str, Field(max_length=MAX_CODE_CHARS)]
    brief_id: str | None = None
    slot: Annotated[int | None, Field(strict=True)] = None


def build_variant(tenant: Tenant, arguments: BuildVariantInput) -> SetBuildResult:
    if arguments.brief_id is not None:
        return variant_sets.build_into_set(
            tenant.roots, tenant.variants, arguments.brief_id, arguments.code, arguments.slot
        )
    if arguments.slot is not None:
        raise SlotRefused("slot names a place in a brief's variant set, so pass brief_id too")
    built = store.build_variant(arguments.code, tenant.variants)
    return SetBuildResult(variant_id=built.variant_id, outcome=built.outcome, output=built.output)


OPERATIONS: Final = (
    operation(
        name="build_variant",
        audience=Audience.AGENT,
        description=BUILD_VARIANT,
        input=BuildVariantInput,
        output=SetBuildResult,
        run=build_variant,
    ),
)
