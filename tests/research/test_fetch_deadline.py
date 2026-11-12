import dataclasses
import datetime
import socket
import ssl
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from cad.research import fetch as fetching
from cad.research.fetch import FetchFailed, Page, PdfFile, Response, Target, fetch

PUBLIC = "93.184.215.14"
LIMIT = 1.0
HEAD = b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"


def certificate(directory: Path) -> tuple[Path, Path, bytes]:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM)
    cert_path, key_path = directory / "cert.pem", directory / "key.pem"
    cert_path.write_bytes(pem)
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert_path, key_path, pem


@dataclasses.dataclass
class Drip:
    port: int
    trust: ssl.SSLContext
    stop: threading.Event


def serve_drip(tmp_path: Path, first: bytes, drop: bytes) -> Iterator[Drip]:
    cert_path, key_path, pem = certificate(tmp_path)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert_path, key_path)
    listener = socket.create_server(("127.0.0.1", 0))
    stop = threading.Event()

    def run() -> None:
        raw, _ = listener.accept()
        with tls.wrap_socket(raw, server_side=True) as conn:
            request = b""
            while b"\r\n\r\n" not in request:
                request += conn.recv(4096)
            try:
                conn.sendall(first)
                while not stop.wait(0.2):
                    conn.sendall(drop)
            except OSError:
                pass

    server = threading.Thread(target=run, daemon=True)
    server.start()
    yield Drip(listener.getsockname()[1], ssl.create_default_context(cadata=pem.decode()), stop)
    stop.set()
    listener.close()
    server.join(5)


def fetch_from(drip: Drip) -> tuple[Page | PdfFile | FetchFailed | None, float]:
    def transport(target: Target, deadline: float) -> Response:
        local = dataclasses.replace(target, address="127.0.0.1")
        return fetching.tls_get(local, deadline, port=drip.port, context=drip.trust)

    answer: list[Page | PdfFile | FetchFailed] = []
    began = time.monotonic()
    worker = threading.Thread(
        target=lambda: answer.append(
            fetch("https://localhost/", resolve=lambda host, port: [PUBLIC], transport=transport)
        ),
        daemon=True,
    )
    worker.start()
    worker.join(LIMIT * 6)
    return (answer[0] if answer else None), time.monotonic() - began


@pytest.fixture
def body_drip(tmp_path: Path) -> Iterator[Drip]:
    yield from serve_drip(tmp_path, HEAD + b"Content-Length: 100000000\r\n\r\n", b"a")


@pytest.fixture
def header_drip(tmp_path: Path) -> Iterator[Drip]:
    yield from serve_drip(tmp_path, HEAD, b"X-Drip: a\r\n")


@pytest.mark.parametrize("drip_fixture", ["body_drip", "header_drip"])
def test_a_page_that_drips_stops_at_the_deadline_over_the_whole_fetch(
    drip_fixture: str, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fetching, "TIMEOUT_SECONDS", LIMIT)
    drip: Drip = request.getfixturevalue(drip_fixture)
    answer, took = fetch_from(drip)
    assert isinstance(answer, FetchFailed), "the fetch was still running well past its deadline"
    assert "TimeoutError" in answer.reason
    assert took < LIMIT * 3
