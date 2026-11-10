from pathlib import Path

from starlette.testclient import TestClient

from cad.accounts.local import LocalIssuer
from cad.accounts.tenants import Tenants
from cad.confirmations.ballot import OS_OPEN
from cad.context_parts.ingest import ingest
from cad.server.hosted import build_app

BASE = "http://127.0.0.1:8765"


def test_the_hosted_app_serves_the_page_without_a_session_and_keeps_its_other_routes(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<div id=root></div>")
    tenants = Tenants(tmp_path / "accounts", 60, OS_OPEN, 0.3, ingest)
    app = build_app(LocalIssuer.open(tmp_path, BASE).issuer(), tenants, web=dist)
    with TestClient(app, base_url=BASE, follow_redirects=False) as client:
        assert client.get("/app/projects/p1").status_code == 200
        assert client.get("/v1/projects").status_code == 401
