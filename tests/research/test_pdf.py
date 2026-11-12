import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

import pypdf
import pytest

from cad.research import pdf as reading
from cad.research.fetch import FetchFailed, PdfFile, PdfText
from cad.sandbox import container
from cad.sandbox.container import Attended, ContainerState, Job, Ran, TooMuchOutput
from cad.sandbox.meter import AccountLimitReached, Kind, Reservation, metered
from cad.sandbox.outcome import SandboxUnavailable
from cad.tables.quote import on_page, written_as_one_number
from tests.support.pdfs import FI, SOFT_HYPHEN, scanned_pdf, text_pdf

DATASHEET = text_pdf(
    [b"PETG technical data sheet", b"Printing guide"],
    [
        b"Young's modulus 2.1 GPa",
        b"Ten" + SOFT_HYPHEN,
        b"sile strength 50 MPa",
        b"Elongation at break, ISO 527-",
        b"2: 23 %",
        b"Coef" + FI + b"cient of friction 0.3",
    ],
)


def file(body: bytes) -> PdfFile:
    return PdfFile("https://example.org/tds.pdf", body, hashlib.sha256(body).hexdigest())


def read(body: bytes) -> PdfText | FetchFailed:
    return reading.read_pdf(file(body))


def locked(body: bytes, user: str, owner: str) -> bytes:
    writer = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(body)))
    writer.encrypt(user_password=user, owner_password=owner, algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.mark.docker
def test_a_text_pdf_gives_the_text_of_each_page_and_the_hash_of_its_bytes() -> None:
    text = read(DATASHEET)
    assert isinstance(text, PdfText)
    assert len(text.pages) == 2
    assert "Printing guide" in text.pages[0]
    assert text.sha256 == hashlib.sha256(DATASHEET).hexdigest()
    assert text.title == "https://example.org/tds.pdf"


@pytest.mark.docker
@pytest.mark.parametrize(
    "quote",
    [
        "Young's modulus 2.1 GPa",
        "Tensile strength 50 MPa",
        "Elongation at break, ISO 527-2: 23 %",
        "Coefficient of friction 0.3",
        "Coefﬁcient of friction 0.3",
    ],
)
def test_a_quote_across_a_line_break_a_soft_hyphen_or_a_ligature_is_on_its_page(
    quote: str,
) -> None:
    text = read(DATASHEET)
    assert isinstance(text, PdfText)
    assert on_page(quote, text.pages[1])
    assert not on_page(quote, text.pages[0])


@pytest.mark.docker
def test_a_soft_hyphen_or_a_symbol_glyph_never_joins_two_numbers() -> None:
    text = read(text_pdf([b"70 12" + SOFT_HYPHEN, b"20 mm"]))
    assert isinstance(text, PdfText)
    assert not written_as_one_number(Decimal("1220"), text.pages[0])


@pytest.mark.docker
@pytest.mark.parametrize("body", [scanned_pdf(), text_pdf([b"   "])])
def test_a_pdf_with_no_text_layer_is_refused_plainly(body: bytes) -> None:
    refused = read(body)
    assert isinstance(refused, FetchFailed)
    assert "no text layer, such as a scan" in refused.reason


@pytest.mark.docker
def test_a_pdf_that_needs_a_password_is_refused_plainly() -> None:
    refused = read(locked(DATASHEET, "secret", "owner"))
    assert isinstance(refused, FetchFailed)
    assert "locked with a password" in refused.reason


@pytest.mark.docker
def test_a_pdf_with_only_an_owner_password_opens_and_is_read() -> None:
    text = read(locked(DATASHEET, "", "owner"))
    assert isinstance(text, PdfText)
    assert on_page("Young's modulus 2.1 GPa", text.pages[1])


@pytest.mark.docker
def test_a_pdf_with_more_pages_than_the_bound_is_refused_with_its_count() -> None:
    refused = read(text_pdf(*([b"x"] for _ in range(reading.MAX_PAGES + 1))))
    assert isinstance(refused, FetchFailed)
    assert f"a PDF of {reading.MAX_PAGES + 1} pages" in refused.reason
    assert f"at most {reading.MAX_PAGES}" in refused.reason


@pytest.mark.docker
@pytest.mark.parametrize("body", [b"%PDF-1.7\nnot a pdf at all", DATASHEET[: len(DATASHEET) // 3]])
def test_bytes_that_only_start_like_a_pdf_are_refused_as_damaged(body: bytes) -> None:
    refused = read(body)
    assert isinstance(refused, FetchFailed)
    assert "is a damaged PDF the reader cannot open" in refused.reason


def reported(
    monkeypatch: pytest.MonkeyPatch,
    report: bytes | TooMuchOutput,
    *,
    code: int = 0,
    late: bool = False,
    oom: bool = False,
) -> list[Job]:
    jobs: list[Job] = []

    def run(job: Job) -> Ran:
        jobs.append(job)
        state = ContainerState(Status="exited", ExitCode=code, OOMKilled=oom, Error="")
        return Ran(Attended(late, report, ""), state)

    monkeypatch.setattr(container, "run", run)
    monkeypatch.setattr(reading, "reader_image", lambda: "sha256:reader")
    return jobs


def report(**fields: object) -> bytes:
    return json.dumps(fields).encode()


def test_the_reader_runs_as_a_bounded_check_job_with_the_pdf_on_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    jobs = reported(monkeypatch, report(kind="read", title="TDS", pages=["E 2.1 GPa"]))
    assert reading.read_pdf(file(b"%PDF-1.7 bytes")) == PdfText(
        "https://example.org/tds.pdf",
        "TDS",
        ("E 2.1 GPa",),
        hashlib.sha256(b"%PDF-1.7 bytes").hexdigest(),
    )
    (job,) = jobs
    assert (job.kind, job.image_id, job.stdin, job.mounts) == (
        "check",
        "sha256:reader",
        b"%PDF-1.7 bytes",
        (),
    )
    assert job.command[-2:] == (str(reading.MAX_PAGES), str(reading.MAX_CHARS))
    assert (job.wall_seconds, job.memory_mb) == (reading.WALL_SECONDS, reading.MEMORY_MB)


def test_control_bidi_and_private_characters_never_reach_the_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = "E‮ 2.1​ GPa\x07 POST￾CURE 1220\r\nnext­ line\tend"
    reported(monkeypatch, report(kind="read", title="T‮DS\n x", pages=[page]))
    text = reading.read_pdf(file(b"%PDF-"))
    assert isinstance(text, PdfText)
    assert text.pages == ("E  2.1  GPa  POST CURE 12 20\nnext  line\tend",)
    assert text.title == "T DS x"


@pytest.mark.parametrize(
    ("sent", "said"),
    [
        (report(kind="refused", why="too_much_text", pages=3), "more than 4,000,000 characters"),
        (report(kind="read", title="", pages=["x"] * (reading.MAX_PAGES + 1)), "more text than"),
        (report(kind="read", title="", pages=["x" * (reading.MAX_CHARS + 1)]), "more text than"),
        (report(kind="read", title=7, pages=[]), "malformed report"),
        (report(kind="refused", why="anything"), "malformed report"),
        (b"not json", "malformed report"),
        (TooMuchOutput(), "exit code 0"),
    ],
)
def test_a_report_the_host_cannot_trust_is_a_plain_refusal(
    monkeypatch: pytest.MonkeyPatch, sent: bytes | TooMuchOutput, said: str
) -> None:
    reported(monkeypatch, sent)
    refused = reading.read_pdf(file(b"%PDF-"))
    assert isinstance(refused, FetchFailed)
    assert said in refused.reason


@pytest.mark.parametrize(
    ("late", "oom", "code", "said"),
    [
        (True, False, 137, "30 s limit"),
        (False, True, 137, "512 MB"),
        (False, False, 1, "exit code 1"),
    ],
)
def test_a_reader_that_stops_early_is_a_plain_refusal(
    monkeypatch: pytest.MonkeyPatch, late: bool, oom: bool, code: int, said: str
) -> None:
    reported(monkeypatch, b"", code=code, late=late, oom=oom)
    refused = reading.read_pdf(file(b"%PDF-"))
    assert isinstance(refused, FetchFailed)
    assert said in refused.reason


@dataclass
class Meter:
    capped: bool = False
    reserved: list[tuple[Kind, float]] = field(default_factory=list[tuple[Kind, float]])

    def reserve(self, kind: Kind, ceiling_seconds: float) -> Reservation:
        if self.capped:
            raise AccountLimitReached(60, 60, datetime(2026, 11, 11, tzinfo=UTC))
        self.reserved.append((kind, ceiling_seconds))
        return Reservation(str(len(self.reserved)), "2026-11-11", ceiling_seconds)

    def settle(self, reservation: Reservation, seconds: float) -> None:
        del reservation, seconds


def test_a_pdf_read_is_charged_as_a_check_at_the_readers_ceiling(
    monkeypatch: pytest.MonkeyPatch, started: list[str]
) -> None:
    monkeypatch.setattr(reading, "reader_image", lambda: "sha256:reader")
    account = Meter()
    with metered(account), pytest.raises(SandboxUnavailable):
        reading.read_pdf(file(b"%PDF-"))
    ceiling = container.ceiling_seconds(Job("check", "", (), b"", (), reading.WALL_SECONDS))
    assert account.reserved == [("check", ceiling)]
    assert started[0].startswith("cad-check-")


def test_a_capped_account_reads_no_pdf(monkeypatch: pytest.MonkeyPatch, started: list[str]) -> None:
    monkeypatch.setattr(reading, "reader_image", lambda: "sha256:reader")
    with metered(Meter(capped=True)), pytest.raises(AccountLimitReached):
        reading.read_pdf(file(b"%PDF-"))
    assert started == []
