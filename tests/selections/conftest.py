import pytest

from cad.accounts.principal import AccountId
from cad.operations.model import Tenant
from cad.operations.tenants import Tenants


@pytest.fixture
def alice(confirming_tenants: Tenants) -> Tenant:
    return confirming_tenants.of(AccountId("user_alice"))
