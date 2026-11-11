from pathlib import Path

import pytest

from cad.accounts.principal import AccountId
from cad.confirmations.waiting import Door
from cad.context_parts.ingest import ingest
from cad.operations.model import Tenant
from cad.operations.tenants import Tenants
from tests.support.browser import Person, local_pages


@pytest.fixture
def tenants(tmp_path: Path, person: Person) -> Tenants:
    person.answer = "confirm"
    door = Door(open_page=local_pages(person, lambda account: tenants.of(account)), wait_seconds=5)
    tenants = Tenants(tmp_path / "accounts", 60, door, ingest)
    return tenants


@pytest.fixture
def alice(tenants: Tenants) -> Tenant:
    return tenants.of(AccountId("user_alice"))
