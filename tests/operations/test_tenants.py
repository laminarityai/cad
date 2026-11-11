from pathlib import Path

import pytest

from cad.accounts.principal import AccountId
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.operations.registry import OPERATIONS
from cad.operations.scorecards import ScorecardInput
from cad.operations.tenants import Tenants
from cad.sandbox.image import BUILD, image_tag
from cad.sandbox.outcome import Build, Built
from cad.variants import entry
from cad.variants.entry import UnknownVariant

ALICE, BOB = AccountId("user_alice"), AccountId("user_bob")
RAIL = b"CASCADE Topology V3, a rail\n"


def tenants(root: Path) -> Tenants:
    return Tenants(root / "accounts", 60, Door(wait_seconds=0.3), ingest)


def test_each_account_has_its_own_partition(tmp_path: Path) -> None:
    accounts = tenants(tmp_path)
    alice, bob = accounts.of(ALICE), accounts.of(BOB)
    assert accounts.of(ALICE) is alice
    assert alice.variants == tmp_path / "accounts" / "user_alice" / "variants"
    assert alice.roots.briefs == tmp_path / "accounts" / "user_alice" / "briefs"
    assert {alice.variants, alice.roots.briefs, alice.roots.projects}.isdisjoint(
        {bob.variants, bob.roots.briefs, bob.roots.projects}
    )


def test_another_account_cannot_read_a_variant_by_its_id(tmp_path: Path) -> None:
    accounts = tenants(tmp_path)
    code = "result = None"
    vid = entry.variant_id(code, image_tag(BUILD))
    entry.save(accounts.of(ALICE).variants, vid, code, Build(outcome=Built(), output=""), RAIL)
    scorecard = next(one for one in OPERATIONS if one.name == "scorecard")
    asked = ScorecardInput(variant_id=vid, material_key="prusament-pla")
    with pytest.raises(UnknownVariant):
        scorecard.run(accounts.of(BOB), asked)
