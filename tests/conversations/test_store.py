import json

import pytest

from cad.conversations import store
from cad.operations.tenants import Tenants
from tests.support.conversations import ALICE, CID


def test_a_conversation_is_stored_under_a_new_directory_as_its_json(tenants: Tenants) -> None:
    tenant = tenants.of(ALICE)
    held = store.create(tenant.conversations, CID, project_id="p-1")
    path = tenant.conversations / f"{CID}.json"
    assert path.read_bytes() == json.dumps(held.model_dump(mode="json")).encode()
    assert store.read(tenant.conversations, CID) == held
    assert [p.name for p in tenant.conversations.iterdir()] == [path.name]


def test_an_unwritable_store_raises_the_os_error_and_leaves_no_temporary(
    tenants: Tenants,
) -> None:
    tenant = tenants.of(ALICE)
    tenant.conversations.mkdir(parents=True)
    tenant.conversations.chmod(0o555)
    try:
        with pytest.raises(PermissionError):
            store.create(tenant.conversations, CID)
    finally:
        tenant.conversations.chmod(0o755)
    assert list(tenant.conversations.iterdir()) == []


def test_a_write_that_cannot_replace_the_record_leaves_no_temporary(tenants: Tenants) -> None:
    tenant = tenants.of(ALICE)
    (tenant.conversations / f"{CID}.json" / "occupied").mkdir(parents=True)
    with pytest.raises(OSError):
        store.create(tenant.conversations, CID)
    assert [p.name for p in tenant.conversations.iterdir()] == [f"{CID}.json"]
