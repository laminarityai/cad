import re

import pytest

from cad.briefs.keys import PER
from cad.briefs.kind import Kind
from cad.operations.guidance import PROPOSE_REQUIREMENTS


@pytest.mark.parametrize(("kind", "per"), PER.items())
def test_the_agent_is_told_the_rule_each_key_refuses_by(kind: Kind, per: str) -> None:
    if per:
        rule = rf"(one \w+(, | and ))*one {kind}((, | and )one \w+)* per {per}"
    else:
        rule = rf"one requirement of each of [\w, ]*\b{kind}\b"
    assert re.search(rule, PROPOSE_REQUIREMENTS), (kind, per)
