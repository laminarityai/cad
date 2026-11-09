"""An account's Tenant, by physical partition.

One layout under a base directory: `briefs/`, `projects/`, `variants/` (with each variant's job
results in `variants/<vid>/jobs/`), `geometry/` and `usage/`. The signing keys are siblings of
each root, so every base has its own keys. The stdio server's base is `~/.cad`, today's paths. The
HTTP server gives account `<aid>` the base `<data root>/accounts/<aid>`. No store is shared between
accounts, content-addressed ones included, so a cache hit cannot reveal another account's geometry.
"""

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from cad.accounts.meter import USAGE, AccountMeter
from cad.accounts.principal import AccountId
from cad.confirmations import http
from cad.confirmations.ballot import Desk, Opener
from cad.confirmations.registry import kinds
from cad.context_parts.store import Ingest
from cad.operations.model import Tenant
from cad.records.roots import Roots

ACCOUNTS: Final = "accounts"


def open_tenant(
    roots: Roots,
    variants: Path,
    geometry: Path,
    cap_seconds: int | None,
    opener: Opener,
    wait_seconds: float,
    ingest: Ingest,
) -> Tenant:
    desk = Desk(roots, kinds(roots), opener, serve=http.serve, wait_seconds=wait_seconds)
    meter = AccountMeter(variants.parent / USAGE, cap_seconds)
    return Tenant(
        roots=roots, variants=variants, geometry=geometry, desk=desk, ingest=ingest, meter=meter
    )


@dataclass
class Tenants:
    """The HTTP server's tenants: one per account, built on first use and kept, since its Desk is
    process state."""

    accounts: Path
    cap_seconds: int
    opener: Opener
    wait_seconds: float
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
                    roots,
                    base / "variants",
                    base / "geometry",
                    self.cap_seconds,
                    self.opener,
                    self.wait_seconds,
                    self.ingest,
                )
                self._open[account] = tenant
            return tenant
