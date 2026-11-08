import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "check_pr_proof.py"


def check(title: str, body: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PR_TITLE": title, "PR_BODY": body}
    return subprocess.run(
        [sys.executable, str(TOOL)], capture_output=True, text=True, check=False, env=env
    )


@pytest.mark.parametrize(
    "body",
    [
        "Here it runs:\n\n![scorecard](https://github.com/user-attachments/assets/1b2c.png)",
        '<img width="600" alt="page" src="https://github.com/user-attachments/assets/9f">',
        "https://github.com/user-attachments/assets/4d7e1f60-0c2a-4b1e-9d3a-5e6f7a8b9c0d",
        "<video src=https://example.com/run.mp4></video>",
        "Recording: [run](https://example.com/live-session.webm)",
    ],
)
def test_a_feature_with_an_attached_image_or_video_passes(body: str) -> None:
    assert check("feat(evals): trace every number", body).returncode == 0


@pytest.mark.parametrize(
    "body",
    [
        "",
        "Tested by hand. Screenshot below.",
        "```\nok   ff3fba59077f1eea: 14 numbers\n```",
        "See https://github.com/laminarityai/cad/actions/runs/42430626478",
    ],
)
def test_a_feature_without_an_attachment_fails_and_says_what_to_add(body: str) -> None:
    done = check("feat(briefs): ask the person on a page", body)
    assert done.returncode == 1
    assert "screenshot or a video" in done.stdout


@pytest.mark.parametrize(
    "title",
    [
        "feat: add materials",
        "feat(checks)!: change the mass check",
        "Feat(server): new tool",
    ],
)
def test_every_spelling_of_a_feature_title_needs_proof(title: str) -> None:
    assert check(title, "no proof").returncode == 1


@pytest.mark.parametrize(
    "title",
    [
        "fix(verify): name pyproject.toml",
        "docs(spec): make friction a defect",
        "ci: require proof on feature PRs",
        "refactor(checks): read requirements with packaging",
        "featureless(x): not a feature",
    ],
)
def test_other_changes_need_no_proof(title: str) -> None:
    assert check(title, "").returncode == 0
