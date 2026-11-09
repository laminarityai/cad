from collections.abc import Sequence
from email.message import Message

import pytest

from cad.research import fetch as fetching
from cad.research.fetch import FetchFailed, Page, Response, Target, fetch

PUBLIC = "93.184.215.14"
HTML = (
    b"<html><head><title>PLA</title><script>x=1</script></head>"
    b"<body>Poisson's ratio 0.36</body></html>"
)


def headers(**fields: str) -> Message:
    message = Message()
    for name, value in fields.items():
        message[name.replace("_", "-")] = value
    return message


def resolver(table: dict[str, Sequence[str]]) -> fetching.Resolve:
    return lambda host, port: table[host]


def serve(*responses: Response) -> tuple[fetching.Transport, list[Target]]:
    seen: list[Target] = []
    queue = list(responses)

    def transport(target: Target, deadline: float) -> Response:
        seen.append(target)
        return queue.pop(0)

    return transport, seen


def ok(body: bytes = HTML, kind: str = "text/html; charset=utf-8") -> Response:
    return Response(200, headers(Content_Type=kind), body)


def test_a_public_html_page_gives_its_title_text_and_hash() -> None:
    transport, seen = serve(ok())
    page = fetch(
        "https://example.org/pla", resolve=resolver({"example.org": [PUBLIC]}), transport=transport
    )
    assert isinstance(page, Page)
    assert page.title == "PLA"
    assert "Poisson's ratio 0.36" in page.text
    assert "x=1" not in page.text
    assert len(page.sha256) == 64
    assert seen == [Target("example.org", PUBLIC, "/pla")]


@pytest.mark.parametrize(
    ("url", "said"),
    [
        ("http://example.org/", "not an https URL"),
        ("https://user:pw@example.org/", "user name or password"),
        ("https://example.org:8443/", "port 8443"),
        ("https:///nohost", "names no host"),
    ],
)
def test_a_url_outside_the_guards_is_refused_before_any_request(url: str, said: str) -> None:
    transport, seen = serve()
    failed = fetch(url, resolve=resolver({"example.org": [PUBLIC]}), transport=transport)
    assert isinstance(failed, FetchFailed)
    assert said in failed.reason
    assert seen == []


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.1",
        "169.254.169.254",
        "::1",
        "fe80::1",
        "::ffff:127.0.0.1",
        "64:ff9b::a9fe:a9fe",
        "2002:7f00:1::1",
        "::7f00:1",
        "::a00:5",
        "::808:808",
        "::",
        "100.64.0.1",
        "224.0.0.1",
    ],
)
def test_a_host_that_resolves_to_a_private_address_is_refused(address: str) -> None:
    transport, seen = serve()
    failed = fetch(
        "https://inside.test/",
        resolve=resolver({"inside.test": [PUBLIC, address]}),
        transport=transport,
    )
    assert isinstance(failed, FetchFailed)
    assert failed.reason == "the host inside.test resolves to a non-public address"
    assert seen == []


def test_a_redirect_is_checked_again_and_refused_when_it_points_inside() -> None:
    transport, seen = serve(Response(302, headers(Location="https://metadata.test/latest"), b""))
    failed = fetch(
        "https://example.org/pla",
        resolve=resolver({"example.org": [PUBLIC], "metadata.test": ["169.254.169.254"]}),
        transport=transport,
    )
    assert isinstance(failed, FetchFailed)
    assert "metadata.test resolves to a non-public address" in failed.reason
    assert "169.254" not in failed.reason
    assert len(seen) == 1


def test_a_redirect_to_http_is_refused() -> None:
    transport, _ = serve(Response(301, headers(Location="http://example.org/pla"), b""))
    failed = fetch(
        "https://example.org/", resolve=resolver({"example.org": [PUBLIC]}), transport=transport
    )
    assert isinstance(failed, FetchFailed)
    assert "not an https URL" in failed.reason


def test_a_redirect_is_followed_and_the_page_names_its_final_url() -> None:
    transport, seen = serve(Response(301, headers(Location="/moved"), b""), ok())
    page = fetch(
        "https://example.org/pla", resolve=resolver({"example.org": [PUBLIC]}), transport=transport
    )
    assert isinstance(page, Page)
    assert page.url == "https://example.org/moved"
    assert [one.path for one in seen] == ["/pla", "/moved"]


def test_endless_redirects_stop() -> None:
    loop = [Response(302, headers(Location="/again"), b"")] * (fetching.MAX_REDIRECTS + 1)
    transport, _ = serve(*loop)
    failed = fetch(
        "https://example.org/", resolve=resolver({"example.org": [PUBLIC]}), transport=transport
    )
    assert isinstance(failed, FetchFailed)
    assert "redirects more than" in failed.reason


@pytest.mark.parametrize(
    ("response", "said"),
    [
        (Response(404, headers(Content_Type="text/html"), b""), "HTTP 404"),
        (ok(b"%PDF", "application/pdf"), "application/pdf"),
        (ok(b"x" * (fetching.MAX_BYTES + 1)), "larger than"),
    ],
)
def test_a_page_the_server_cannot_read_is_refused(response: Response, said: str) -> None:
    transport, _ = serve(response)
    failed = fetch(
        "https://example.org/", resolve=resolver({"example.org": [PUBLIC]}), transport=transport
    )
    assert isinstance(failed, FetchFailed)
    assert said in failed.reason


def test_a_host_that_does_not_resolve_is_refused() -> None:
    def nowhere(host: str, port: int) -> Sequence[str]:
        raise OSError("no such host")

    failed = fetch("https://nowhere.test/", resolve=nowhere, transport=serve()[0])
    assert isinstance(failed, FetchFailed)
    assert "does not resolve" in failed.reason


def test_a_transport_error_is_a_reason_not_an_exception() -> None:
    def broken(target: Target, deadline: float) -> Response:
        raise TimeoutError("slow")

    failed = fetch(
        "https://example.org/", resolve=resolver({"example.org": [PUBLIC]}), transport=broken
    )
    assert isinstance(failed, FetchFailed)
    assert "TimeoutError" in failed.reason


def test_a_url_with_characters_outside_ascii_is_requested_percent_encoded() -> None:
    transport, seen = serve(ok())
    fetch(
        "https://example.org/GEP-Ertacetal™%20C.html?q=é",
        resolve=resolver({"example.org": [PUBLIC]}),
        transport=transport,
    )
    assert seen == [Target("example.org", PUBLIC, "/GEP-Ertacetal%E2%84%A2%20C.html?q=%C3%A9")]
