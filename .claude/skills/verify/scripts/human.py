#!/usr/bin/env python3
"""The scripted person for verify runs: `cad-server --opener <this file>` runs it with the page URL.

Usage: human.py <url>. Environment: CAD_HUMAN_LOG (required, a path for JSON lines), CAD_HUMAN_DELAY
(seconds before answering, default 1), CAD_HUMAN_ANSWER (confirm or decline, default confirm),
CAD_HUMAN_EDIT (optional, "<shown>=<typed>": type <typed> into the field whose placeholder is
<shown>, such as "150 g=120 g"). It logs the HTTP status of a GET with the token stripped, a GET
with a wrong token, a GET with the token and each section of that page with its title, each row's
headline, its brief and quotes, the answer POST and a replayed POST, then the spent token as
{"spent_token": ...}, so a run can grep the agent's transcript for it.
The server does not wait for it, so it records its own failures in the log.
"""

from __future__ import annotations

import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode, urlsplit

SECTION = re.compile(r'<section class="item">(.*?)</section>', re.DOTALL)
QUOTE = re.compile(r'<q class="origin">(.*?)</q>', re.DOTALL)
BRIEF = re.compile(r'<blockquote class="brief">(.*?)</blockquote>', re.DOTALL)
TITLE = re.compile(r"<h2>(.*?)</h2>", re.DOTALL)
HEADLINE = re.compile(r"<strong>(.*?)</strong>", re.DOTALL)
FIELD = re.compile(r'<input name="(edit-[0-9]+-[0-9a-f]{16})" placeholder="([^"]*)"')


def fetch(
    url: str, body: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, str]:
    sent = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(sent, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def section_of(section: str) -> dict[str, object]:
    brief = html.unescape(next(iter(BRIEF.findall(section)), ""))
    quotes = [html.unescape(quote) for quote in QUOTE.findall(section)]
    in_brief = bool(quotes) and all(quote in brief for quote in quotes)
    title = html.unescape(next(iter(TITLE.findall(section)), ""))
    headlines = [html.unescape(headline) for headline in HEADLINE.findall(section)]
    return {
        "title": title,
        "headlines": headlines,
        "brief": brief,
        "quotes": quotes,
        "quotes_in_brief": in_brief,
    }


def main(url: str, log: Path) -> None:
    delay = float(os.environ.get("CAD_HUMAN_DELAY", "1"))
    answer = os.environ.get("CAD_HUMAN_ANSWER", "confirm")
    parts = urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    base, _, token = url.rpartition("/")

    def record(entry: dict[str, object]) -> None:
        with log.open("a") as file:
            file.write(json.dumps(entry) + "\n")

    record({"step": "no token", "status": fetch(base + "/")[0]})
    record({"step": "wrong token", "status": fetch(base + "/" + "A" * len(token))[0]})
    status, page = fetch(url)
    sections = [section_of(found) for found in SECTION.findall(page)]
    record(
        {
            "step": "page",
            "status": status,
            "sections": sections,
            "quotes_in_brief": bool(sections) and all(s["quotes_in_brief"] for s in sections),
        }
    )
    time.sleep(delay)
    shown, _, typed = os.environ.get("CAD_HUMAN_EDIT", "").partition("=")
    fields = {n: typed for n, p in FIELD.findall(page) if shown and html.unescape(p) == shown}
    record({"step": "edit", "shown": shown, "typed": typed, "fields": len(fields)})
    note = "" if answer == "confirm" else "scripted person declined"
    form = urlencode({"answer": answer, "note": note, **fields}).encode()
    headers = {"Origin": origin, "Content-Type": "application/x-www-form-urlencoded"}
    record({"step": answer, "status": fetch(url, form, headers)[0]})
    record({"step": "replay", "status": fetch(url, form, headers)[0]})
    record({"spent_token": token})


if __name__ == "__main__":
    log_path = os.environ.get("CAD_HUMAN_LOG")
    if len(sys.argv) != 2 or not log_path:
        sys.exit("usage: CAD_HUMAN_LOG=<path> human.py <url>")
    try:
        main(sys.argv[1], Path(log_path))
    except Exception as error:  # the server discards this process's output, so log every failure
        with Path(log_path).open("a") as file:
            file.write(json.dumps({"error": f"{type(error).__name__}: {error}"}) + "\n")
        raise
