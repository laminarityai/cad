from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from cad.web.static import ASSET_CACHE, NOT_BUILT, PAGE_CACHE, web_routes

PAGE = "<!doctype html><div id=root></div>"
LANDING = "<!doctype html><h1>landing</h1>"


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    (tmp_path / "dist" / "assets").mkdir(parents=True)
    (tmp_path / "dist" / "index.html").write_text(PAGE)
    (tmp_path / "dist" / "landing.html").write_text(LANDING)
    (tmp_path / "dist" / "assets" / "app-abc123.js").write_text("export {}")
    (tmp_path / "secret.txt").write_text("outside")
    return tmp_path / "dist"


def client(dist: Path) -> TestClient:
    return TestClient(Starlette(routes=web_routes(dist)), follow_redirects=False)


def test_the_root_is_the_landing_page_and_is_not_cached(dist: Path) -> None:
    answer = client(dist).get("/")
    assert answer.status_code == 200
    assert answer.text == LANDING
    assert answer.headers["cache-control"] == PAGE_CACHE
    assert answer.headers["content-type"].startswith("text/html")


def test_the_root_answers_a_head_request(dist: Path) -> None:
    assert client(dist).head("/").status_code == 200


def test_the_landing_page_is_not_the_app_page(dist: Path) -> None:
    assert client(dist).get("/app/").text == PAGE


def test_the_app_without_its_slash_still_goes_to_the_app(dist: Path) -> None:
    answer = client(dist).get("/app")
    assert answer.status_code == 307
    assert answer.headers["location"] == "/app/"


def test_a_build_without_the_landing_page_says_so_at_the_root(dist: Path) -> None:
    (dist / "landing.html").unlink()
    answer = client(dist).get("/")
    assert answer.status_code == 503
    assert answer.text == NOT_BUILT
    assert client(dist).get("/app/").status_code == 200


def test_the_app_page_is_not_cached(dist: Path) -> None:
    answer = client(dist).get("/app/")
    assert answer.status_code == 200
    assert answer.text == PAGE
    assert answer.headers["cache-control"] == PAGE_CACHE


def test_a_route_of_the_app_gets_the_page(dist: Path) -> None:
    answer = client(dist).get("/app/projects/p1/briefs/b1")
    assert answer.status_code == 200
    assert answer.text == PAGE


def test_an_asset_is_cached_for_good(dist: Path) -> None:
    answer = client(dist).get("/app/assets/app-abc123.js")
    assert answer.status_code == 200
    assert answer.text == "export {}"
    assert answer.headers["cache-control"] == ASSET_CACHE


def test_a_missing_asset_is_not_the_page(dist: Path) -> None:
    assert client(dist).get("/app/assets/gone.js").status_code == 404


def test_a_path_cannot_leave_the_directory(dist: Path) -> None:
    answer = client(dist).get("/app/%2e%2e/secret.txt")
    assert "outside" not in answer.text
    assert answer.status_code == 404


def test_a_directory_traversal_in_a_route_gets_only_the_page(dist: Path) -> None:
    answer = client(dist).get("/app/..%2f..%2fsecret")
    assert "outside" not in answer.text


def test_an_unbuilt_app_says_so(tmp_path: Path) -> None:
    answer = client(tmp_path / "missing").get("/app/")
    assert answer.status_code == 503
    assert answer.text == NOT_BUILT
