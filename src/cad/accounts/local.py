"""The local issuer, which stands in for Clerk on 127.0.0.1.

It mints tokens shaped like Clerk's and signs them with an RSA key kept at
`<data root>/local-issuer.pem`. The HTTP server trusts it only when it listens on a loopback
address and has no Clerk configuration, so tests, evals and local development need no Clerk
instance. `cad-token` prints a token for a local server, for curl and scripted clients.
"""

import argparse
import hashlib
import os
import secrets
import sys
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from cad.accounts.principal import account_id
from cad.accounts.tokens import Issuer
from cad.records.roots import DATA_ROOT

ISSUER_URL: Final = "http://127.0.0.1/cad-local-issuer"
KEY_FILE: Final = "local-issuer.pem"
TTL_SECONDS: Final = 3600


@dataclass(frozen=True, slots=True)
class LocalIssuer:
    private_key: RSAPrivateKey
    resource: str
    origin: str

    @staticmethod
    def open(root: Path, base_url: str) -> "LocalIssuer":
        """`base_url` is the server's own URL, such as `http://127.0.0.1:8765`."""
        path = root / KEY_FILE
        if not path.exists():
            _create_key(path)
        loaded = serialization.load_pem_private_key(path.read_bytes(), password=None)
        if not isinstance(loaded, RSAPrivateKey):
            raise ValueError(f"{path} does not hold an RSA private key")
        base = base_url.rstrip("/")
        return LocalIssuer(loaded, f"{base}/mcp", base)

    @staticmethod
    def in_memory(base_url: str) -> "LocalIssuer":
        """A key no file holds, for the stdio server's own page: no other process can mint."""
        base = base_url.rstrip("/")
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        return LocalIssuer(key, f"{base}/mcp", base)

    @property
    def kid(self) -> str:
        der = self.private_key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return "ins_local_" + hashlib.sha256(der).hexdigest()[:16]

    def issuer(self) -> Issuer:
        public, kid = self.private_key.public_key(), self.kid
        return Issuer(
            ISSUER_URL,
            lambda wanted: public if wanted == kid else None,
            self.resource,
            frozenset({self.origin}),
        )

    def mint_agent(self, account: str, ttl: int = TTL_SECONDS) -> str:
        claims = {
            "sub": account,
            "aud": [self.resource],
            "client_id": "client_cad_local",
            "scope": "profile email",
            "jti": f"oat_{secrets.token_hex(12)}",
        }
        return self._sign(claims, "at+jwt", ttl)

    def mint_person(self, account: str, ttl: int = TTL_SECONDS) -> str:
        claims = {
            "sub": account,
            "sid": f"sess_{secrets.token_hex(12)}",
            "azp": self.origin,
            "jti": secrets.token_hex(10),
            "v": 2,
        }
        return self._sign(claims, "JWT", ttl)

    def _sign(self, claims: Mapping[str, object], typ: str, ttl: int) -> str:
        now = int(time.time())
        timed = {**claims, "iss": ISSUER_URL, "iat": now, "nbf": now, "exp": now + ttl}
        headers = {"typ": typ, "kid": self.kid}
        return jwt.encode(timed, self.private_key, algorithm="RS256", headers=headers)


def _create_key(path: Path) -> None:
    """Written beside its final name and linked into place, so two processes that start at once
    agree on one key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}-{secrets.token_hex(8)}")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as file:
            file.write(pem)
        with suppress(FileExistsError):
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cad-token", description="Print a token from the local issuer of a local cad-http."
    )
    parser.add_argument("kind", choices=("agent", "person"))
    parser.add_argument("account")
    parser.add_argument("--url", default="http://127.0.0.1:8765", help="the server's own URL")
    parser.add_argument("--root", type=Path, default=DATA_ROOT, help="the server's data root")
    args = parser.parse_args(argv)
    issuer = LocalIssuer.open(args.root, args.url)
    account = account_id(args.account)
    mint = issuer.mint_agent if args.kind == "agent" else issuer.mint_person
    print(mint(account))
    return 0


if __name__ == "__main__":
    sys.exit(main())
