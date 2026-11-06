from pathlib import Path

CI_WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def uv_commands() -> list[str]:
    commands: list[str] = []
    for line in CI_WORKFLOW.read_text().splitlines():
        key, _, value = line.strip().removeprefix("- ").partition(":")
        if key == "run" and value.strip().startswith("uv "):
            commands.append(value.strip())
    return commands


def test_ci_installs_and_runs_from_the_committed_lockfile() -> None:
    assert uv_commands() == ["uv sync --locked", "uv run --locked verify"]
