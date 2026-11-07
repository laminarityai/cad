import os
import secrets
import stat
from pathlib import Path
from typing import Final

from cad.checks.result import CheckRun
from cad.sandbox import host
from cad.sandbox.outcome import SandboxUnavailable
from cad.scorecard.model import Scorecard
from cad.variants import entry

SCORECARD: Final = "scorecard.json"


def score_variant(
    variant_id: str, material_key: str, root: Path = entry.VARIANTS_ROOT
) -> Scorecard:
    card = scorecard_of(host.run_checks(variant_id, material_key, root))
    store(card, root)
    return card


def scorecard_of(run: CheckRun) -> Scorecard:
    return Scorecard(
        variant_id=run.variant_id,
        material_key=run.material_key,
        table_version=run.table_version,
        image_digest=run.image_digest,
        brep_sha256=run.brep_sha256,
        step=run.step,
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
        raise SandboxUnavailable.hiding_path(
            f"cannot store the scorecard of variant {card.variant_id}", error, path
        ) from error
    finally:
        temporary.unlink(missing_ok=True)
    return path
