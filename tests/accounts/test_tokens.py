import base64
import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from cad.accounts.clerk import ClerkMisconfigured, clerk_issuer, frontend_api
from cad.accounts.local import LocalIssuer, main
from cad.accounts.principal import AccountId, AgentToken, PersonSession
from cad.accounts.tokens import Issuer, Verifier, jwks_keys
from cad.conversations.model import NotAConversation
from tests.support.hosted import BASE

CLERK = "https://clerk.example.test"
KID = "ins_test"


def verifier(issuer: LocalIssuer) -> Verifier:
    return Verifier(issuer.issuer())


def test_an_agent_token_verifies_only_as_an_agent(local: LocalIssuer) -> None:
    token = local.mint_agent("user_alice")
    agent = verifier(local).agent(token)
    assert isinstance(agent, AgentToken)
    assert agent.account == "user_alice"
    assert verifier(local).person(token) is None


def test_a_session_token_verifies_only_as_a_person(local: LocalIssuer) -> None:
    token = local.mint_person("user_alice")
    person = verifier(local).person(token)
    assert isinstance(person, PersonSession)
    assert person.account == "user_alice"
    assert verifier(local).agent(token) is None


def test_an_agent_token_for_another_resource_is_refused(local: LocalIssuer, tmp_path: Path) -> None:
    other = LocalIssuer.open(tmp_path, "http://127.0.0.1:9999")
    assert verifier(local).agent(other.mint_agent("user_alice")) is None


def test_a_session_token_from_another_origin_is_refused(local: LocalIssuer, tmp_path: Path) -> None:
    other = LocalIssuer.open(tmp_path, "http://127.0.0.1:9999")
    assert verifier(local).person(other.mint_person("user_alice")) is None


def test_a_token_signed_by_another_key_is_refused(local: LocalIssuer, tmp_path: Path) -> None:
    stranger = LocalIssuer.open(tmp_path / "elsewhere", BASE)
    assert verifier(local).agent(stranger.mint_agent("user_alice")) is None
    assert verifier(local).person(stranger.mint_person("user_alice")) is None


def test_an_expired_token_is_refused(local: LocalIssuer) -> None:
    assert verifier(local).agent(local.mint_agent("user_alice", ttl=-60)) is None


@pytest.mark.parametrize("account", ["../user_bob", "user/bob", "", "x" * 65])
def test_a_subject_that_is_not_an_account_id_is_refused(local: LocalIssuer, account: str) -> None:
    assert verifier(local).agent(local.mint_agent(account)) is None


def test_garbage_is_refused(local: LocalIssuer) -> None:
    assert verifier(local).agent("not a token") is None
    assert verifier(local).person("") is None


class Jwks(BaseHTTPRequestHandler):
    body = b""

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: Any) -> None:
        del format, args


@pytest.fixture
def clerk_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks_url(clerk_key: rsa.RSAPrivateKey) -> Iterator[str]:
    public = json.loads(RSAAlgorithm.to_jwk(clerk_key.public_key()))
    Jwks.body = json.dumps(
        {"keys": [{**public, "kid": KID, "use": "sig", "alg": "RS256"}]}
    ).encode()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Jwks)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/.well-known/jwks.json"
    server.shutdown()


def clerk_token(key: rsa.RSAPrivateKey, typ: str, claims: dict[str, object]) -> str:
    now = int(time.time())
    timed = {"iss": CLERK, "sub": "user_2abc", "iat": now, "nbf": now, "exp": now + 60, **claims}
    return jwt.encode(timed, key, algorithm="RS256", headers={"typ": typ, "kid": KID})


def test_clerk_shaped_tokens_verify_against_the_instance_jwks(
    clerk_key: rsa.RSAPrivateKey, jwks_url: str
) -> None:
    origin = "https://cad.example.test"
    clerk = Verifier(Issuer(CLERK, jwks_keys(jwks_url), f"{origin}/mcp", frozenset({origin})))
    oauth = clerk_token(
        clerk_key,
        "at+jwt",
        {"aud": [f"{origin}/mcp"], "client_id": "client_x", "jti": "oat_1", "scope": "profile"},
    )
    session = clerk_token(clerk_key, "JWT", {"sid": "sess_1", "azp": origin, "v": 2})
    assert clerk.agent(oauth) == AgentToken(
        account=AccountId("user_2abc"), token_id="oat_1", client_id="client_x"
    )
    assert clerk.person(session) == PersonSession(
        account=AccountId("user_2abc"), session_id="sess_1"
    )
    assert clerk.agent(session) is None
    assert clerk.person(oauth) is None
    no_audience = clerk_token(clerk_key, "at+jwt", {"client_id": "client_x", "jti": "oat_2"})
    assert clerk.agent(no_audience) is None


def publishable(host: str, prefix: str = "pk_test_") -> str:
    return prefix + base64.b64encode(f"{host}$".encode()).decode().rstrip("=")


def test_the_frontend_api_comes_from_the_publishable_key() -> None:
    assert frontend_api(publishable("well-hagfish-71.clerk.accounts.dev")) == (
        "https://well-hagfish-71.clerk.accounts.dev"
    )
    assert frontend_api(publishable("clerk.cad.example", "pk_live_")) == "https://clerk.cad.example"
    with pytest.raises(ClerkMisconfigured):
        frontend_api("sk_test_abc")


def test_clerk_is_off_without_a_publishable_key_and_needs_a_public_url() -> None:
    assert clerk_issuer({}) is None
    key = publishable("well-hagfish-71.clerk.accounts.dev")
    with pytest.raises(ClerkMisconfigured, match="CAD_PUBLIC_URL"):
        clerk_issuer({"CLERK_PUBLISHABLE_KEY": key})
    issuer = clerk_issuer({"CLERK_PUBLISHABLE_KEY": key, "CAD_PUBLIC_URL": "https://cad.example/"})
    assert issuer is not None
    assert (issuer.url, issuer.resource) == (
        "https://well-hagfish-71.clerk.accounts.dev",
        "https://cad.example/mcp",
    )


def test_an_agent_token_carries_its_conversation_and_a_malformed_one_is_refused(
    local: LocalIssuer,
) -> None:
    plain = verifier(local).agent(local.mint_agent("user_alice"))
    held = verifier(local).agent(local.mint_agent("user_alice", conversation="c-1"))
    assert plain is not None and plain.conversation is None
    assert held is not None and held.conversation == "c-1"
    assert verifier(local).agent(local.mint_agent("user_alice", conversation="../x")) is None
    assert verifier(local).agent(local.mint_agent("user_alice", conversation="")) is None


def test_cad_token_names_a_conversation_for_an_agent_token_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = ["--root", str(tmp_path)]
    assert main(["agent", "user_alice", "--conversation", "c-1", *root]) == 0
    token = capsys.readouterr().out.strip()
    assert Verifier(LocalIssuer.open(tmp_path, BASE).issuer()).agent(token) is not None
    with pytest.raises(SystemExit):
        main(["person", "user_alice", "--conversation", "c-1", *root])
    with pytest.raises(NotAConversation):
        main(["agent", "user_alice", "--conversation", "../x", *root])
