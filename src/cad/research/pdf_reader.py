"""Runs in the reader image, never on the host: `python -I -c <this file> <max pages> <max chars>`
with the PDF on stdin. It writes one JSON report to stdout, the text of each page or why there is
none. The host writes every sentence the agent reads, so a report carries only codes and text."""

import json
import resource
import sys

import pypdfium2  # pyright: ignore[reportMissingTypeStubs]
import pypdfium2.raw  # pyright: ignore[reportMissingTypeStubs]

CPU_SECONDS = 20


def main() -> None:
    max_pages, max_chars = int(sys.argv[1]), int(sys.argv[2])
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 5))
    sys.stdout.write(json.dumps(read(sys.stdin.buffer.read(), max_pages, max_chars)))


def read(data: bytes, max_pages: int, max_chars: int) -> dict[str, object]:
    try:
        document = pypdfium2.PdfDocument(data)
    except pypdfium2.PdfiumError as error:
        locked = error.err_code in (  # pyright: ignore[reportUnknownMemberType]
            pypdfium2.raw.FPDF_ERR_PASSWORD,
            pypdfium2.raw.FPDF_ERR_SECURITY,
        )
        return {"kind": "refused", "why": "password" if locked else "damaged"}
    count = len(document)
    if count > max_pages:
        return {"kind": "refused", "why": "too_many_pages", "pages": count}
    pages: list[str] = []
    total = 0
    try:
        for index in range(count):
            text = document[index].get_textpage().get_text_range()
            total += len(text)
            if total > max_chars:
                return {"kind": "refused", "why": "too_much_text", "pages": count}
            pages.append(text)
    except pypdfium2.PdfiumError:
        return {"kind": "refused", "why": "damaged"}
    title = document.get_metadata_value("Title") or ""  # pyright: ignore[reportUnknownMemberType]
    return {"kind": "read", "title": title, "pages": pages}


if __name__ == "__main__":
    main()
