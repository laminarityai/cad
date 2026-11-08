"""Fail a feature PR whose description has no screenshot or video attached.

A PR adds a feature when its title is a conventional-commit `feat`. Its body must then embed
or link an image or a video: a Markdown image, an <img> or <video> tag, a GitHub attachment
link, or a link to an image or video file. Text alone, such as pasted output, does not count.
CI passes the PR's title and body in PR_TITLE and PR_BODY.
"""

import os
import re
import sys

FEATURE = re.compile(r"feat(\([^)]*\))?!?:", re.IGNORECASE)
PROOF = (
    re.compile(r"!\[[^\]]*\]\([^)\s]+\)"),
    re.compile(r"<(img|video)\b", re.IGNORECASE),
    re.compile(r"https://github\.com/(user-attachments/assets|[\w.-]+/[\w.-]+/assets)/\S+"),
    re.compile(r"https?://\S+\.(png|jpe?g|gif|webp|mp4|mov|webm)\b", re.IGNORECASE),
)
MISSING = (
    "This PR adds a feature, so its description needs a screenshot or a video of the feature "
    "working. For a server feature with no screen, attach a screenshot or recording of the real "
    "run, such as a claude -p session or cad-call output. Pasted text alone does not count. "
    "Drag the file into the PR description on GitHub, then save."
)


def needs_proof(title: str) -> bool:
    return FEATURE.match(title.strip()) is not None


def has_proof(body: str) -> bool:
    return any(pattern.search(body) for pattern in PROOF)


def main() -> int:
    title = os.environ.get("PR_TITLE", "")
    body = os.environ.get("PR_BODY", "")
    if needs_proof(title) and not has_proof(body):
        print(MISSING)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
