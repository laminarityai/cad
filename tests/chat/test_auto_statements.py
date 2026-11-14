from cad.accounts.principal import AccountId
from cad.chat.auto_driver import project_statements
from cad.operations.briefs import (
    CreateBriefInput,
    ProposeRequirementsInput,
    RequirementDraft,
    create_brief,
    propose_requirements,
)
from cad.operations.tenants import Tenants
from cad.projects.model import ProjectId
from tests.support.chat import ALICE

UNDER = RequirementDraft.model_validate(
    {"target": {"kind": "max_mass", "mass": {"magnitude": 40, "unit": "g"}}, "quote": "40 g"}
)


def test_a_stop_report_names_a_row_proposed_on_another_brief_of_the_project(
    tenants: Tenants,
) -> None:
    alice = tenants.of(AccountId(ALICE))
    box = create_brief(alice, CreateBriefInput(text="A box"))
    lid = create_brief(alice, CreateBriefInput(text="A lid under 40 g", project_id=box.project_id))
    rows = propose_requirements(
        alice, ProposeRequirementsInput(brief_id=lid.brief_id, requirements=[UNDER])
    ).requirements
    said = project_statements(alice.roots, ProjectId(box.project_id))
    assert [said[one.requirement.id] for one in rows] == ["Mass at most 40 g"]
