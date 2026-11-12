"""A brief that holds a variant, and the stored `fea` result that closes the result rule."""

from pathlib import Path

from cad.checks import job_store
from cad.checks.jobs import Background, JobResult, JobSpec
from cad.checks.report import SPECS, build_request, unknown_for_all
from cad.checks.result import StepMissing
from cad.tables.materials import load_materials
from cad.variant_sets import store
from cad.variants.entry import VariantId
from tests.support.load_cases import Part, shelf
from tests.support.session import Session

WORDS = "A wall shelf bracket. Will it hold 5 kg? About 49 N, and not more than 2 mm of sag"
FEA_BUDGET = Background(wall_seconds=600, memory_mb=2048, tmpfs_mb=768)


def row(case: Part, quote: str = "Will it hold 5 kg") -> Part:
    return {"target": {"kind": "min_safety_factor", "load": case, "factor": 2}, "quote": quote}


def deflection(case: Part, quote: str = "not more than 2 mm of sag") -> Part:
    target = {"kind": "max_deflection", "load": case, "deflection": {"magnitude": 2, "unit": "mm"}}
    return {"target": target, "quote": quote}


def heavier(force: float = 98.0) -> Part:
    return shelf({"magnitude": force, "unit": "N"})


async def brief_of(s: Session, *rows: Part) -> str:
    brief_id = (await s.call("create_brief", text=WORDS))["brief_id"]
    if rows:
        await s.call("propose_requirements", brief_id=brief_id, requirements=list(rows))
    return brief_id


def build_into_the_set(s: Session, brief_id: str, code: str = "# a bracket\n") -> str:
    """Put a variant in the brief's set, as build_variant would, without a container."""
    variant_id = s.variant(code)
    store.join(s.roots.projects, store.set_key(s.roots, brief_id), code, VariantId(variant_id))
    return variant_id


def fea_job(root: Path, variant_id: str) -> JobSpec:
    (root / variant_id).mkdir(parents=True, exist_ok=True)
    fea = tuple(spec for spec in SPECS if spec.id == "fea")
    return JobSpec(
        root,
        variant_id,
        "b" * 64,
        fea,
        FEA_BUDGET,
        build_request("prusament-pla", load_materials(), fea),
    )


def unknown_fea(reason: str = "the faces were not found") -> JobResult:
    return JobResult(
        check_image_digest="sha256:" + "i" * 64,
        step=StepMissing(reason=reason),
        results=unknown_for_all(reason, tuple(spec for spec in SPECS if spec.id == "fea")),
    )


def store_a_fea_result(s: Session, variant_id: str) -> None:
    """What one score leaves on disk for a variant: its `fea` result, here unknown."""
    job_store.write(fea_job(s.variants, variant_id), unknown_fea())
