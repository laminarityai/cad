"""An account's Tenant, by physical partition.

One layout under a base directory: `briefs/`, `projects/`, `variants/` (with each variant's job
results in `variants/<vid>/jobs/`), `geometry/`, `conversations/` and `usage/`. The signing keys
are siblings of each root, so every base has its own keys. The stdio server's base is `~/.cad`,
today's paths. The HTTP server gives account `<aid>` the base `<data root>/accounts/<aid>`. No
store is shared between accounts, content-addressed ones included, so a cache hit cannot reveal
another account's geometry.
"""

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from cad.accounts.meter import USAGE, AccountMeter
from cad.accounts.principal import AccountId
from cad.confirmations.waiting import Bell, Door
from cad.context_parts.store import Ingest
from cad.operations.model import Tenant
from cad.records.roots import Roots

ACCOUNTS: Final = "accounts"
CONVERSATIONS: Final = "conversations"


def open_tenant(
    account: AccountId,
    roots: Roots,
    variants: Path,
    geometry: Path,
    cap_seconds: int | None,
    door: Door,
    ingest: Ingest,
) -> Tenant:
    return Tenant(
        account=account,
        roots=roots,
        variants=variants,
        geometry=geometry,
        conversations=variants.parent / CONVERSATIONS,
        bell=Bell(),
        door=door,
        ingest=ingest,
        meter=AccountMeter(variants.parent / USAGE, cap_seconds),
    )


@dataclass
class Tenants:
    """The HTTP server's tenants: one per account, built on first use and kept, since its Bell is
    process state that the page and the waiting tool call share."""

    accounts: Path
    cap_seconds: int
    door: Door
    ingest: Ingest
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _open: dict[AccountId, Tenant] = field(default_factory=dict[AccountId, Tenant])

    def of(self, account: AccountId) -> Tenant:
        with self._lock:
            tenant = self._open.get(account)
            if tenant is None:
                base = self.accounts / account
                roots = Roots(base / "briefs", base / "projects")
                tenant = open_tenant(
                    account,
                    roots,
                    base / "variants",
                    base / "geometry",
                    self.cap_seconds,
                    self.door,
                    self.ingest,
                )
                self._open[account] = tenant
            return tenant
