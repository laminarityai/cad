"""The Clerk instance, read from environment variables only. No key is ever committed.

`CLERK_PUBLISHABLE_KEY` names the instance: it is `pk_test_` or `pk_live_` and the base64 of the
Frontend API host followed by `$`, which is how Clerk's own MCP tools derive the Frontend API URL.
That URL is the `iss` of every token, the authorization server named in our Protected Resource
Metadata, and the base of the JWKS URL. `CAD_PUBLIC_URL` is this server's public origin: `/mcp`
under it is the resource an agent token's `aud` must include, and it is the origin a session
token's `azp` must name.
"""

import base64
import binascii
from collections.abc import Mapping
from typing import Final

from cad.accounts.tokens import Issuer, jwks_keys

PUBLISHABLE_KEY: Final = "CLERK_PUBLISHABLE_KEY"
PUBLIC_URL: Final = "CAD_PUBLIC_URL"
KEY_PREFIXES: Final = ("pk_test_", "pk_live_")


class ClerkMisconfigured(ValueError):
    pass


def frontend_api(publishable_key: str) -> str:
    prefix = next((one for one in KEY_PREFIXES if publishable_key.startswith(one)), None)
    if prefix is None:
        raise ClerkMisconfigured(f"{PUBLISHABLE_KEY} does not start with pk_test_ or pk_live_")
    encoded = publishable_key.removeprefix(prefix)
    try:
        decoded = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True).decode()
    except (binascii.Error, UnicodeDecodeError) as error:
        raise ClerkMisconfigured(f"{PUBLISHABLE_KEY} is not a Clerk publishable key") from error
    host = decoded.removesuffix("$")
    if not decoded.endswith("$") or not host or "/" in host:
        raise ClerkMisconfigured(f"{PUBLISHABLE_KEY} does not name a Frontend API host")
    return f"https://{host}"


def clerk_issuer(environ: Mapping[str, str]) -> Issuer | None:
    """None when `CLERK_PUBLISHABLE_KEY` is not set."""
    publishable = environ.get(PUBLISHABLE_KEY)
    if not publishable:
        return None
    public = environ.get(PUBLIC_URL, "").rstrip("/")
    if not public.startswith("https://"):
        raise ClerkMisconfigured(f"{PUBLIC_URL} must be this server's https:// origin")
    url = frontend_api(publishable)
    return Issuer(
        url, jwks_keys(f"{url}/.well-known/jwks.json"), f"{public}/mcp", frozenset({public})
    )
