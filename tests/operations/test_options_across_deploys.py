"""A deploy that edits only code no build depends on leaves every option current. One that edits a
file a build depends on rebuilds an option once, and the rebuild is the same option everywhere."""

from pathlib import Path

import pytest

from cad.accounts.principal import AccountId
from cad.geometry import store
from cad.operations import exports, reads
from cad.operations.model import Tenant
from cad.operations.scorecards import (
    ScorecardInput,
    ScoreVariantInput,
    score_variant,
    scorecard,
)
from cad.operations.tenants import Tenants
from cad.operations.variants import BuildVariantInput, build_variant
from cad.projects.model import ProjectId
from cad.sandbox import container, image
from cad.sandbox.container import Job, Ran
from cad.selections import mint
from cad.selections.model import Picked
from cad.variants import entry
from tests.support.deploys import digest_after_editing
from tests.support.selections import Project, confirmed, tessellated
from tests.support.set_parts import PLATE

pytestmark = [pytest.mark.anyio, pytest.mark.docker]


@pytest.fixture
def alice(confirming_tenants: Tenants) -> Tenant:
    return confirming_tenants.of(AccountId("user_alice"))


@pytest.fixture
def builds(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    real_run = container.run
    started: list[str] = []

    def run(job: Job) -> Ran:
        if job.kind == "build":
            started.append(job.kind)
        return real_run(job)

    monkeypatch.setattr(container, "run", run)
    return started


def scored(tenant: Tenant, project: Project) -> str:
    asked = BuildVariantInput(
        code=PLATE, brief_id=project.brief, material_key="prusament-pla", material_reason="light"
    )
    built = build_variant(tenant, asked)
    score_variant(tenant, ScoreVariantInput(variant_id=built.variant_id, brief_id=project.brief))
    return built.variant_id


def shown(tenant: Tenant, project: Project) -> list[tuple[str, list[str]]]:
    asked = reads.VariantSetInput(project_id=project.project, brief_id=project.brief)
    members = reads.variant_set(tenant, asked).members
    return [(one.variant_id, [rev.variant_id for rev in one.revisions]) for one in members]


def deploy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, name: str) -> None:
    monkeypatch.setattr(entry, "TRUST_DIGEST", digest_after_editing(tmp_path, name))


async def test_a_deploy_that_edits_only_check_code_leaves_a_scored_option_current(
    alice: Tenant, builds: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = await confirmed(alice)
    option = scored(alice, project)
    builds.clear()
    deploy(monkeypatch, tmp_path, "sandbox/host.py")
    assert shown(alice, project) == [(option, [option])]
    card = scorecard(alice, ScorecardInput(variant_id=option, brief_id=project.brief))
    assert (card.variant_id, card.rebuilt_from, card.pending) == (option, None, ())
    again = score_variant(alice, ScoreVariantInput(variant_id=option, brief_id=project.brief))
    assert (again.variant_id, again.rebuilt_from) == (option, None)
    assert builds == []


async def test_a_deploy_that_edits_build_code_rebuilds_once_and_every_read_names_the_rebuild(
    alice: Tenant, builds: list[str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    project = await confirmed(alice)
    option = scored(alice, project)
    builds.clear()
    deploy(monkeypatch, tmp_path, "sandbox/container.py")
    card = score_variant(alice, ScoreVariantInput(variant_id=option, brief_id=project.brief))
    rebuilt = card.variant_id
    assert (builds, card.rebuilt_from) == (["build"], option)
    assert rebuilt != option
    assert shown(alice, project) == [(rebuilt, [rebuilt])]
    stem = exports.stem_of(alice, project.brief, rebuilt)
    assert stem == exports.stem_of(alice, project.brief, option)
    assert stem.endswith("rev1")
    held = entry.open_entry(alice.variants, rebuilt, image.image_tag(image.BUILD))
    store.write(alice.geometry, tessellated().model_copy(update={"brep_sha256": held.brep_sha256}))
    picked = Picked(variant_id=rebuilt, part=True)
    record = mint.mint(
        alice.roots,
        ProjectId(project.project),
        picked,
        variants=alice.variants,
        geometry=alice.geometry,
    )
    assert (record.slot, record.revision, record.variant_id) == (1, 1, rebuilt)

    builds.clear()
    deploy(monkeypatch, tmp_path, "sandbox/runner.py")
    later = score_variant(alice, ScoreVariantInput(variant_id=rebuilt, brief_id=project.brief))
    assert (builds, later.rebuilt_from, later.material_key) == (["build"], rebuilt, "prusament-pla")
    assert shown(alice, project) == [(later.variant_id, [later.variant_id])]
    assert exports.stem_of(alice, project.brief, rebuilt) == stem
