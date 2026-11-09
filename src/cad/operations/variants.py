from typing import Annotated, Final

from pydantic import Field

from cad.operations.model import Audience, Input, Tenant, operation
from cad.sandbox import container, host
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import MAX_MEMBERS, SetBuildResult
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
    "compare, and variant_set names its slot. Build 3 to 5 different variants. Code already in "
    "the set keeps its slot. A build for a brief with no confirmed requirements, or for new code "
    "when the set is full, is refused before it starts. If the set fills while a build runs, "
    "the build finishes and is stored, but the error says it joined no set and names its "
    "variant id. Without brief_id the variant joins no set."
)


class BuildVariantInput(Input):
    code: Annotated[str, Field(max_length=MAX_CODE_CHARS)]
    brief_id: str | None = None


def build_variant(tenant: Tenant, arguments: BuildVariantInput) -> SetBuildResult:
    if arguments.brief_id is not None:
        return variant_sets.build_into_set(
            tenant.roots, tenant.variants, arguments.brief_id, arguments.code
        )
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
