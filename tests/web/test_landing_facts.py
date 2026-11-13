import json
from pathlib import Path
from typing import Any, cast

from cad.checks.container.suite import CHECKS
from cad.operations.guidance import BUILD_FIRST, OPTIONS
from cad.tables.materials import load_materials
from cad.variant_sets.model import MAX_MEMBERS

FACTS = Path(__file__).resolve().parents[2] / "web" / "src" / "features" / "landing" / "facts.json"


def repo_facts() -> dict[str, str]:
    """The value the landing page writes for each fact it measured in this repo, by fact id."""
    rows = cast("list[dict[str, Any]]", json.loads(FACTS.read_text())["facts"])
    return {row["id"]: row["value"] for row in rows if row["source"]["kind"] == "repo"}


def test_the_page_counts_the_checks_the_suite_holds() -> None:
    assert repo_facts()["checks"] == str(len(CHECKS))


def test_the_page_counts_the_materials_the_table_holds() -> None:
    assert repo_facts()["materials"] == str(len(load_materials().materials))


def test_the_page_says_the_options_the_agent_is_told_to_build() -> None:
    low, _, high = repo_facts()["options"].partition(" to ")
    assert int(high) == MAX_MEMBERS
    assert f"{low} to {high} options" in BUILD_FIRST + OPTIONS
