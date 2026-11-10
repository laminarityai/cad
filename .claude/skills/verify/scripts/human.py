#!/usr/bin/env python3
"""The scripted person for verify runs: `cad-server --opener <this file>` runs it with a link.

Usage: human.py <link>, where the link is
`http://127.0.0.1:<port>/local/sign-in?token=<person JWT>&project=<project id>`.
Environment: CAD_HUMAN_LOG (required, a path for JSON lines), CAD_HUMAN_DELAY (seconds before
answering, default 1), CAD_HUMAN_ANSWER (confirm or decline, default confirm),
CAD_HUMAN_EDIT (optional, "<shown>=<typed>": type <typed> into the field whose placeholder is
<shown>, such as "150 g=120 g"). It logs the status of a GET of the page with no cookie
(`no session`), the sign-in link followed with a cookie jar and each section of the page it lands
on with its title, each row's headline, its brief and quotes (`page`, with the final path), the
answer POST with the page's snapshot field and an Origin header, a byte-for-byte replay of it,
then the person JWT as {"spent_token": ...}, so a run can grep the agent's transcript for it.
The server does not wait for it, so it records its own failures in the log, with the JWT left out.
"""

from __future__ import annotations

import html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

SECTION = re.compile(r'<section class="item">(.*?)</section>', re.DOTALL)
QUOTE = re.compile(r'<q class="origin">(.*?)</q>', re.DOTALL)
BRIEF = re.compile(r'<blockquote class="brief">(.*?)</blockquote>', re.DOTALL)
TITLE = re.compile(r"<h2>(.*?)</h2>", re.DOTALL)
HEADLINE = re.compile(r"<strong>(.*?)</strong>", re.DOTALL)
FIELD = re.compile(r'<input name="(edit-[0-9]+-[0-9a-f]{16})" placeholder="([^"]*)"')
SNAPSHOT = re.compile(r'<input type="hidden" name="snapshot" value="([^"]*)">')


def fetch(
    opener: urllib.request.OpenerDirector,
    url: str,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """The status, the body and the path the response came from, after any redirect."""
    sent = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with opener.open(sent, timeout=10) as response:
            return response.status, response.read().decode(), urlsplit(response.url).path
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode(), urlsplit(error.url).path


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


def main(link: str, log: Path) -> None:
    token = ""

    def record(entry: dict[str, object]) -> None:
        with log.open("a") as file:
            file.write(json.dumps(entry) + "\n")

    try:
        delay = float(os.environ.get("CAD_HUMAN_DELAY", "1"))
        answer = os.environ.get("CAD_HUMAN_ANSWER", "confirm")
        parts = urlsplit(link)
        query = parse_qs(parts.query)
        token = query["token"][0]
        origin = f"{parts.scheme}://{parts.netloc}"
        address = f"{origin}/projects/{query['project'][0]}/confirm"
        bare = urllib.request.build_opener()
        record({"step": "no session", "status": fetch(bare, address)[0]})
        jar = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        status, page, path = fetch(jar, link)
        sections = [section_of(found) for found in SECTION.findall(page)]
        record(
            {
                "step": "page",
                "status": status,
                "path": path,
                "sections": sections,
                "quotes_in_brief": bool(sections) and all(s["quotes_in_brief"] for s in sections),
            }
        )
        snapshot = SNAPSHOT.search(page)
        if snapshot is None:
            raise LookupError(f"the page at status {status} has no snapshot field to answer")
        time.sleep(delay)
        shown, _, typed = os.environ.get("CAD_HUMAN_EDIT", "").partition("=")
        fields = {n: typed for n, p in FIELD.findall(page) if shown and html.unescape(p) == shown}
        record({"step": "edit", "shown": shown, "typed": typed, "fields": len(fields)})
        note = "" if answer == "confirm" else "scripted person declined"
        form = urlencode(
            {"snapshot": html.unescape(snapshot[1]), "answer": answer, "note": note, **fields}
        ).encode()
        headers = {"Origin": origin, "Content-Type": "application/x-www-form-urlencoded"}
        record({"step": answer, "status": fetch(jar, address, form, headers)[0]})
        record({"step": "replay", "status": fetch(jar, address, form, headers)[0]})
        record({"spent_token": token})
    except Exception as error:  # the server discards this process's output, so log every failure
        record({"error": f"{type(error).__name__}: {error}".replace(token, "<token>")})
        raise


if __name__ == "__main__":
    log_path = os.environ.get("CAD_HUMAN_LOG")
    if len(sys.argv) != 2 or not log_path:
        sys.exit("usage: CAD_HUMAN_LOG=<path> human.py <sign-in link>")
    main(sys.argv[1], Path(log_path))
