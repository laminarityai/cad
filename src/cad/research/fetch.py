import hashlib
import http.client
import ipaddress
import socket
import ssl
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from email.message import Message
from html.parser import HTMLParser
from typing import Final
from urllib.parse import urljoin, urlsplit

MAX_BYTES: Final = 4 * 1024 * 1024
TIMEOUT_SECONDS: Final = 15.0
MAX_REDIRECTS: Final = 5
PORT: Final = 443
USER_AGENT: Final = "cad-research/1 (reads one cited page; https://github.com/laminarityai/cad)"
TEXT_TYPES: Final = frozenset({"text/html", "application/xhtml+xml", "text/plain"})
SKIPPED_TAGS: Final = frozenset({"script", "style", "noscript", "template", "svg"})

_NAT64: Final = ipaddress.IPv6Network("64:ff9b::/96")

type Address = ipaddress.IPv4Address | ipaddress.IPv6Address
type Resolve = Callable[[str, int], Sequence[str]]


@dataclass(frozen=True, slots=True)
class Target:
    host: str
    address: str
    path: str


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: Message
    body: bytes


type Transport = Callable[[Target, float], Response]


@dataclass(frozen=True, slots=True)
class Page:
    url: str
    title: str
    text: str
    sha256: str


@dataclass(frozen=True, slots=True)
class FetchFailed:
    reason: str


class _Refused(Exception):
    pass


def fetch(
    url: str, *, resolve: Resolve | None = None, transport: Transport | None = None
) -> Page | FetchFailed:
    resolve = resolve or _resolve
    transport = transport or _tls_get
    deadline = time.monotonic() + TIMEOUT_SECONDS
    current = url
    try:
        for _ in range(MAX_REDIRECTS + 1):
            target = _target(current, resolve)
            response = transport(target, deadline)
            location = response.headers.get("Location")
            if response.status in {301, 302, 303, 307, 308} and location:
                current = urljoin(current, location)
                continue
            return _page(current, response)
    except _Refused as refused:
        return FetchFailed(str(refused))
    except (OSError, ValueError) as error:
        return FetchFailed(f"the fetch of {current} failed: {type(error).__name__}: {error}")
    return FetchFailed(f"{url} redirects more than {MAX_REDIRECTS} times")


def _target(url: str, resolve: Resolve) -> Target:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise _Refused(f"{url} is not an https URL; the server fetches only https")
    if parts.username is not None or parts.password is not None:
        raise _Refused(f"{url} carries a user name or password; the server sends no credentials")
    host = parts.hostname
    if not host:
        raise _Refused(f"{url} names no host")
    if parts.port not in (None, PORT):
        raise _Refused(f"{url} names port {parts.port}; the server fetches only port {PORT}")
    try:
        addresses = [_address(one) for one in resolve(host, PORT)]
    except (OSError, UnicodeError) as error:
        raise _Refused(f"the host {host} does not resolve: {error}") from error
    if not addresses:
        raise _Refused(f"the host {host} does not resolve")
    private = [str(one) for one in addresses if not _public(one)]
    if private:
        raise _Refused(
            f"the host {host} resolves to {', '.join(private)}, which is not a public address"
        )
    path = parts.path or "/"
    return Target(host, str(addresses[0]), f"{path}?{parts.query}" if parts.query else path)


def _address(text: str) -> Address:
    """An IPv6 address that carries an IPv4 one, mapped or through NAT64, is judged as the IPv4
    address it reaches."""
    address = ipaddress.ip_address(text.split("%", 1)[0])
    if not isinstance(address, ipaddress.IPv6Address):
        return address
    if address.ipv4_mapped is not None:
        return address.ipv4_mapped
    if address in _NAT64:
        return ipaddress.IPv4Address(int(address) & 0xFFFFFFFF)
    return address


def _public(address: Address) -> bool:
    """Private, loopback, link-local (which holds 169.254.169.254, the cloud metadata address),
    shared, reserved and multicast addresses are all refused."""
    return address.is_global and not address.is_multicast


def _resolve(host: str, port: int) -> Sequence[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


class _Pinned(http.client.HTTPSConnection):
    def __init__(self, target: Target, timeout: float) -> None:
        self._tls = ssl.create_default_context()
        super().__init__(target.host, PORT, timeout=timeout, context=self._tls)
        self._address = target.address

    def connect(self) -> None:
        raw = socket.create_connection((self._address, PORT), timeout=self.timeout)
        self.sock = self._tls.wrap_socket(raw, server_hostname=self.host)


def _tls_get(target: Target, deadline: float) -> Response:
    connection = _Pinned(target, _left(deadline))
    try:
        connection.request(
            "GET",
            target.path,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html, application/xhtml+xml, text/plain",
                "Accept-Encoding": "identity",
            },
        )
        response = connection.getresponse()
        body = bytearray()
        while len(body) <= MAX_BYTES:
            _left(deadline)
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            body += chunk
        return Response(response.status, response.msg, bytes(body))
    finally:
        connection.close()


def _left(deadline: float) -> float:
    left = deadline - time.monotonic()
    if left <= 0:
        raise TimeoutError(f"the page took longer than {TIMEOUT_SECONDS:g} s")
    return left


def _page(url: str, response: Response) -> Page:
    if response.status != 200:
        raise _Refused(f"{url} answered HTTP {response.status}, not 200")
    if len(response.body) > MAX_BYTES:
        raise _Refused(f"{url} is larger than {MAX_BYTES // 2**20} MiB")
    kind = response.headers.get_content_type()
    if kind not in TEXT_TYPES:
        raise _Refused(f"{url} is {kind}; the server reads only HTML and plain text pages")
    charset = response.headers.get_content_charset() or "utf-8"
    try:
        decoded = response.body.decode(charset, errors="replace")
    except LookupError:
        decoded = response.body.decode("utf-8", errors="replace")
    title, text = _html_text(decoded) if kind != "text/plain" else ("", decoded)
    return Page(url, title or url, text, hashlib.sha256(response.body).hexdigest())


class _TextOf(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title: list[str] = []
        self._skipping = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag in SKIPPED_TAGS:
            self._skipping += 1
        self._in_title = self._in_title or tag == "title"
        self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_TAGS and self._skipping:
            self._skipping -= 1
        if tag == "title":
            self._in_title = False
        self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        elif not self._skipping:
            self.parts.append(data)


def _html_text(html: str) -> tuple[str, str]:
    parser = _TextOf()
    parser.feed(html)
    parser.close()
    return " ".join("".join(parser.title).split())[:200], "".join(parser.parts)
