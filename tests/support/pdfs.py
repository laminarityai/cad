"""Small PDFs written byte by byte, so a test of the reader names exactly what is in the file.

Each page draws its lines in Helvetica, one under the other. The font's encoding maps byte 0x80
to the "fi" ligature glyph and 0x81 to a soft hyphen, as typeset datasheets carry them."""

from collections.abc import Sequence

FI = b"\x80"
SOFT_HYPHEN = b"\x81"
# One grey pixel drawn over the page, as a scanner leaves a page: an image and no text.
SCAN = b"q 612 0 0 792 0 0 cm BI /W 1 /H 1 /BPC 8 /CS /G ID \x80 EI Q"


def text_pdf(*pages: Sequence[bytes]) -> bytes:
    """A PDF whose pages draw these lines of text, one line under the other."""
    return pdf([_lines(page) for page in pages])


def scanned_pdf(pages: int = 1) -> bytes:
    return pdf([SCAN] * pages)


def pdf(contents: Sequence[bytes]) -> bytes:
    font = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding"
        b" << /Type /Encoding /BaseEncoding /WinAnsiEncoding /Differences [128 /fi /hyphen] >> >>"
    )
    count = len(contents)
    pages_at = 3
    first_page = 4
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 3 0 R >>",
        font,
        b"<< /Type /Pages /Kids ["
        + b" ".join(b"%d 0 R" % (first_page + 2 * n) for n in range(count))
        + b"] /Count %d >>" % count,
    ]
    for n, content in enumerate(contents):
        stream = first_page + 2 * n + 1
        objects.append(
            b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792]"
            b" /Resources << /Font << /F1 2 0 R >> >> /Contents %d 0 R >>" % (pages_at, stream)
        )
        objects.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
    return _file(objects)


def _lines(lines: Sequence[bytes]) -> bytes:
    shown = b" ".join(b"(%s) Tj T*" % _escaped(line) for line in lines)
    return b"BT /F1 12 Tf 14 TL 72 720 Td " + shown + b" ET"


def _escaped(line: bytes) -> bytes:
    return line.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _file(objects: Sequence[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref,
    )
    return bytes(out)
