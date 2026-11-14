import json
from pathlib import Path

import yaml

from cad.checks.report import IMAGE_TAG, Request, build_request, parse
from cad.checks.result import CheckRun, Materials, StepMissing, StepStored, per_body, single_key
from cad.sandbox import container, image, stage
from cad.sandbox.bodies import bodies_sha256
from cad.sandbox.container import Job
from cad.sandbox.outcome import SandboxUnavailable
from cad.tables.materials import TABLE_PATH, MaterialsTable, load_materials
from cad.variants import entry


def check_job(brep: bytes, image_id: str, request: Request, wall_seconds: int) -> Job:
    cpu_seconds = str(wall_seconds * container.CPUS)
    report_cap = str(container.REPORT_CAP)
    command = ("python", "-I", "-c", stage.BOOT, cpu_seconds, json.dumps(request.wire), report_cap)
    return Job("check", image_id, command, brep, (stage.check_mount(),), wall_seconds)


def run_checks(
    variant_id: str,
    material: Materials,
    root: Path = entry.VARIANTS_ROOT,
    *,
    wall_seconds: int = container.WALL_SECONDS,
) -> CheckRun:
    """Raises
        UnknownVariant       not 16 lowercase hex digits, or no such entry
        StaleVariant         the entry does not re-derive to its own id: stored before the fix for
                             issue #6, under another image, or edited. `OutdatedVariant` when
                             its signed record pins the code an older sandbox stored
        NotBuilt             the stored outcome is not `built`
        SandboxUnavailable   Docker, the image, the store, or the materials table is unusable
    Returns a `CheckRun` with one result per check, always. A container that times out, runs out of
    memory, dies, or sends a malformed report yields `unknown` results, never an exception and
    never `pass`. A STEP too large for the report is left out, and the results stand. A material
    key that is not in the table makes `mass` `unknown`. A variant of named bodies takes a key
    for each body, in the order its body list names them, and ValueError says when it is not.
    """
    held = entry.open_entry(root, variant_id, image.image_tag(image.BUILD))
    request = build_request(material, materials_table(), bodies=held.bodies)
    return run_request(variant_id, request, root, wall_seconds=wall_seconds)


def run_request(
    variant_id: str,
    request: Request,
    root: Path = entry.VARIANTS_ROOT,
    *,
    wall_seconds: int = container.WALL_SECONDS,
) -> CheckRun:
    held = entry.open_entry(root, variant_id, image.image_tag(image.BUILD))
    image_id = image.current_image(IMAGE_TAG)
    try:
        job = check_job(held.brep, image_id, request, wall_seconds)
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot stage the check sources for variant {held.id}", error, stage.STAGE_ROOT
        ) from error
    ran = container.run(job)
    parsed = parse(ran, request, job)
    try:
        step = (
            parsed.step
            if isinstance(parsed.step, StepMissing)
            else StepStored(sha256=held.attach_step(parsed.step))
        )
    except OSError as error:
        raise SandboxUnavailable.hiding_host(
            f"cannot store the STEP of variant {held.id}", error, held.directory / entry.STEP
        ) from error
    return CheckRun(
        variant_id=held.id,
        material_key=single_key(request.material),
        materials=per_body(request.material),
        bodies_sha256=bodies_sha256(request.bodies),
        table_version=request.table_version,
        check_image_tag=IMAGE_TAG,
        check_image_digest=image_id,
        brep_sha256=held.brep_sha256,
        step=step,
        results=parsed.results,
        timed_out=parsed.timed_out,
    )


def materials_table() -> MaterialsTable:
    try:
        return load_materials()
    except (OSError, ValueError, yaml.YAMLError) as error:
        raise SandboxUnavailable.hiding_host(
            "cannot read the materials table", error, TABLE_PATH
        ) from error
