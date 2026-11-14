import hashlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from cad.accounts.principal import AccountId
from cad.briefs.store import UnknownBrief
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.geometry import job, store
from cad.geometry.model import TessellationFailed, UnknownMesh
from cad.operations import reads
from cad.operations.briefs import (
    CreateBriefInput,
    ListRequirementsInput,
    ProposeRequirementsInput,
    RequirementDraft,
    create_brief,
    list_requirements,
    propose_requirements,
)
from cad.operations.confirmation import AskToConfirmInput, ask_to_confirm
from cad.operations.model import Tenant
from cad.operations.server import NoArguments
from cad.operations.tenants import Tenants
from cad.projects.model import UnknownProject
from cad.sandbox.bodies import Body
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.variant_sets import store as variant_sets
from cad.variant_sets.model import Chosen, MaterialChoice
from cad.variants import entry
from cad.variants.entry import UnknownVariant
from tests.support.browser import local_pages

if TYPE_CHECKING:
    from tests.support.browser import Person

pytestmark = pytest.mark.anyio

ALICE, BOB = AccountId("user_alice"), AccountId("user_bob")
TEXT = "A plate under 150 g"
UNDER_150 = RequirementDraft.model_validate(
    {
        "target": {"kind": "max_mass", "mass": {"magnitude": 150, "unit": "g"}},
        "quote": "under 150 g",
    }
)
RAIL = b"CASCADE Topology V3, a rail\n"


@pytest.fixture
def accounts(tmp_path: Path, person: "Person") -> Tenants:
    person.answer = "confirm"
    door = Door(open_page=local_pages(person, lambda account: tenants.of(account)), wait_seconds=5)
    tenants = Tenants(tmp_path / "accounts", 60, door, ingest)
    return tenants


@pytest.fixture
def alice(accounts: Tenants) -> Tenant:
    return accounts.of(ALICE)


@pytest.fixture
def bob(accounts: Tenants) -> Tenant:
    return accounts.of(BOB)


def proposed(tenant: Tenant, project_id: str | None = None) -> tuple[str, str]:
    created = create_brief(tenant, CreateBriefInput(text=TEXT, project_id=project_id))
    propose_requirements(
        tenant, ProposeRequirementsInput(brief_id=created.brief_id, requirements=[UNDER_150])
    )
    return created.project_id, created.brief_id


async def confirmed(tenant: Tenant) -> tuple[str, str]:
    project, brief = proposed(tenant)
    answer = await ask_to_confirm(tenant, AskToConfirmInput(project_id=project))
    assert answer.status == "answered"
    return project, brief


def built(tenant: Tenant, code: str) -> str:
    vid = entry.variant_id(code, image_tag(BUILD))
    entry.save(tenant.variants, vid, code, Build(outcome=Built(), output=""), RAIL)
    return vid


def joined(tenant: Tenant, brief: str, code: str, slot: int | None = None) -> str:
    vid = built(tenant, code)
    key = variant_sets.set_key(tenant.roots, brief)
    variant_sets.join(tenant.roots.projects, key, code, entry.VariantId(vid), slot)
    return vid


def test_list_projects_names_each_project_with_its_briefs_newest_project_first(
    alice: Tenant,
) -> None:
    assert reads.list_projects(alice, NoArguments()).projects == ()
    first, first_brief = proposed(alice)
    _, second_brief = proposed(alice, first)
    other, other_brief = proposed(alice)
    listed = reads.list_projects(alice, NoArguments()).projects
    assert [(one.project_id, one.brief_ids) for one in listed] == [
        (other, (other_brief,)),
        (first, (first_brief, second_brief)),
    ]


def test_project_summarises_each_brief_and_says_which_proposal_is_confirmed(alice: Tenant) -> None:
    project, brief = proposed(alice)
    view = reads.project(alice, reads.ProjectInput(project_id=project))
    assert [(one.brief_id, one.proposals, one.confirmed_proposal) for one in view.briefs] == [
        (brief, 1, None)
    ]


async def test_a_confirmed_proposal_shows_in_the_project(alice: Tenant) -> None:
    project, _ = await confirmed(alice)
    [summary] = reads.project(alice, reads.ProjectInput(project_id=project)).briefs
    assert summary.confirmed_proposal == 1


def test_a_brief_reads_the_part_name_it_was_created_with(alice: Tenant) -> None:
    named = create_brief(alice, CreateBriefInput(text=TEXT, name="  Desk box "))
    unnamed = create_brief(alice, CreateBriefInput(text=TEXT))
    assert (
        list_requirements(alice, ListRequirementsInput(brief_id=named.brief_id)).name == "Desk box"
    )
    assert list_requirements(alice, ListRequirementsInput(brief_id=unnamed.brief_id)).name is None


def test_an_unknown_project_is_refused(alice: Tenant) -> None:
    with pytest.raises(UnknownProject):
        reads.project(alice, reads.ProjectInput(project_id="p-" + "0" * 16))


async def test_the_variant_set_lists_slots_with_their_revisions(alice: Tenant) -> None:
    project, brief = await confirmed(alice)
    first = joined(alice, brief, "result = 1")
    joined(alice, brief, "result = 2")
    third = joined(alice, brief, "result = 3")
    revised = joined(alice, brief, "result = 4", slot=1)
    seen = reads.variant_set(alice, reads.VariantSetInput(project_id=project, brief_id=brief))
    assert [(one.slot, one.revision, len(one.revisions)) for one in seen.members] == [
        (1, 2, 2),
        (2, 1, 1),
        (3, 1, 1),
    ]
    assert seen.members[0].variant_id == revised
    assert [one.variant_id for one in seen.members[0].revisions] == [first, revised]
    assert seen.members[2].variant_id == third


async def test_a_member_never_scored_has_no_card_etag_and_names_its_material(
    alice: Tenant,
) -> None:
    project, brief = await confirmed(alice)
    vid = built(alice, "result = 1")
    key = variant_sets.set_key(alice.roots, brief)
    choice = MaterialChoice(key="prusament-pla", reason="light")
    variant_sets.join(
        alice.roots.projects,
        key,
        "result = 1",
        entry.VariantId(vid),
        None,
        lambda _, __: Chosen(material=choice),
    )
    asked = reads.VariantSetInput(project_id=project, brief_id=brief, material_key="prusament-pla")
    [member] = reads.variant_set(alice, asked).members
    assert (member.card_etag, member.material_name) == (None, "Prusament PLA")


async def test_an_unconfirmed_brief_has_an_empty_set_and_joins_before_a_confirmation(
    alice: Tenant,
) -> None:
    project, brief = proposed(alice)
    asked = reads.VariantSetInput(project_id=project, brief_id=brief)
    assert reads.variant_set(alice, asked).members == ()
    vid = joined(alice, brief, "result = 1")
    assert [m.variant_id for m in reads.variant_set(alice, asked).members] == [vid]


def test_a_brief_outside_the_named_project_has_no_set(alice: Tenant) -> None:
    _, brief = proposed(alice)
    with pytest.raises(UnknownProject):
        reads.variant_set(alice, reads.VariantSetInput(project_id="p-" + "0" * 16, brief_id=brief))


def test_view_names_the_brep_and_whether_its_mesh_is_stored(alice: Tenant) -> None:
    vid = built(alice, "result = 1")
    sha = hashlib.sha256(RAIL).hexdigest()
    pending = reads.view(alice, reads.VariantInput(variant_id=vid))
    assert (pending.brep_sha256, pending.mesh) == (sha, "pending")
    stored = TessellationFailed(brep_sha256=sha, version=job.VERSION, reason="unreadable")
    store.write(alice.geometry, stored)
    failed = reads.view(alice, reads.VariantInput(variant_id=vid))
    assert (failed.mesh, failed.mesh_url) == ("failed", None)


def test_mesh_refuses_a_brep_that_is_not_tessellated(alice: Tenant) -> None:
    sha = hashlib.sha256(RAIL).hexdigest()
    asked = reads.MeshInput(version=job.VERSION, brep_sha256=sha)
    with pytest.raises(UnknownMesh):
        reads.mesh(alice, asked)
    store.write(
        alice.geometry, TessellationFailed(brep_sha256=sha, version=job.VERSION, reason="x")
    )
    with pytest.raises(UnknownMesh):
        reads.mesh(alice, asked)


async def test_another_account_reads_nothing_of_alices(alice: Tenant, bob: Tenant) -> None:
    project, brief = await confirmed(alice)
    vid = joined(alice, brief, "result = 1")
    sha = hashlib.sha256(RAIL).hexdigest()
    store.write(
        alice.geometry, TessellationFailed(brep_sha256=sha, version=job.VERSION, reason="x")
    )
    assert reads.list_projects(bob, NoArguments()).projects == ()
    with pytest.raises(UnknownProject):
        reads.project(bob, reads.ProjectInput(project_id=project))
    with pytest.raises(UnknownBrief):
        reads.variant_set(bob, reads.VariantSetInput(project_id=project, brief_id=brief))
    with pytest.raises(UnknownVariant):
        reads.view(bob, reads.VariantInput(variant_id=vid))
    with pytest.raises(UnknownMesh):
        reads.mesh(bob, reads.MeshInput(version=job.VERSION, brep_sha256=sha))


async def test_a_body_s_own_made_of_shows_on_the_slot_before_it_is_scored(alice: Tenant) -> None:
    created = create_brief(alice, CreateBriefInput(text="A PLA part with a steel plate"))
    made_of = [
        RequirementDraft.model_validate({"target": target, "quote": quote})
        for target, quote in (
            ({"kind": "made_of", "material": "prusament-pla"}, "PLA part"),
            (
                {"kind": "made_of", "material": "cliffs-hot-rolled-cs-type-b", "body": "plate"},
                "steel plate",
            ),
        )
    ]
    propose_requirements(
        alice, ProposeRequirementsInput(brief_id=created.brief_id, requirements=made_of)
    )
    answer = await ask_to_confirm(alice, AskToConfirmInput(project_id=created.project_id))
    assert answer.status == "answered"
    code = "result = 'gears on a plate'"
    bodies = (Body(name="plate", solids=(0,)), Body(name="gear", solids=(1,)))
    vid = entry.variant_id(code, image_tag(BUILD))
    entry.save(alice.variants, vid, code, Build(outcome=Built(bodies=bodies), output=""), RAIL)
    key = variant_sets.set_key(alice.roots, created.brief_id)
    variant_sets.join(alice.roots.projects, key, code, entry.VariantId(vid), None)
    asked = reads.VariantSetInput(project_id=created.project_id, brief_id=created.brief_id)
    [member] = reads.variant_set(alice, asked).members
    assert member.material is None
    assert [(one.body, one.key, one.set_by.kind) for one in member.body_materials] == [
        ("plate", "cliffs-hot-rolled-cs-type-b", "requirement"),
        ("gear", "prusament-pla", "requirement"),
    ]


async def test_an_option_an_older_sandbox_stored_shows_its_rebuild_once_it_is_rebuilt(
    alice: Tenant,
) -> None:
    project, brief = await confirmed(alice)
    code = "result = 1"
    old = entry.variant_id(code, "cad-sandbox:before-a-deploy")
    entry.save(alice.variants, old, code, Build(outcome=Built(), output=""), RAIL)
    key = variant_sets.set_key(alice.roots, brief)
    variant_sets.join(alice.roots.projects, key, code, old, None)
    asked = reads.VariantSetInput(project_id=project, brief_id=brief)
    [before] = reads.variant_set(alice, asked).members
    assert before.variant_id == old
    rebuilt = built(alice, code)
    [after] = reads.variant_set(alice, asked).members
    assert after.variant_id == rebuilt
    assert [one.variant_id for one in after.revisions] == [rebuilt]
    assert reads.view(alice, reads.VariantInput(variant_id=after.variant_id)).variant_id == rebuilt
