import logging
import os
import secrets
import stat
from pathlib import Path
from typing import Final

from cad.checks.result import CheckRun
from cad.sandbox import host
from cad.sandbox.image import context_tar, current_image, image_tag
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard.model import Scorecard
from cad.variants import entry

SCORECARD: Final = "scorecard.json"
LOG = logging.getLogger(__name__)


def score_variant(
    variant_id: str, material_key: str, root: Path = entry.VARIANTS_ROOT
) -> Scorecard:
    tag = image_tag(context_tar())
    image_before = current_image(tag)
    run = host.run_checks(variant_id, material_key, root)
    image_after = current_image(run.image_tag)
    if image_after != image_before:
        raise SandboxUnavailable(
            f"the sandbox image {run.image_tag} changed while variant {run.variant_id} was "
            f"checked, from {image_before} to {image_after}; no scorecard was stored"
        )
    card = scorecard_of(run, image_after)
    store(card, root)
    return card


def scorecard_of(run: CheckRun, image_digest: str) -> Scorecard:
    return Scorecard(
        variant_id=run.variant_id,
        material_key=run.material_key,
        table_version=run.table_version,
        image_digest=image_digest,
        brep_sha256=run.brep_sha256,
        step_sha256=run.step_sha256,
        results=run.results,
    )


def store(card: Scorecard, root: Path) -> Path:
    directory = root / card.variant_id
    path = directory / SCORECARD
    temporary = directory / f".scorecard-{secrets.token_hex(8)}"
    try:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise NotADirectoryError(str(directory))
        temporary.write_text(card.model_dump_json(indent=2) + "\n")
        os.replace(temporary, path)
    except OSError as error:
        LOG.error("cannot store %s: %s", path, error)
        raise SandboxUnavailable(
            f"cannot store the scorecard of variant {card.variant_id}: {type(error).__name__}"
        ) from error
    finally:
        temporary.unlink(missing_ok=True)
    return path
