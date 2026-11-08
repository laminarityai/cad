from cad.checks.report import DEPENDENCIES


def test_the_files_every_check_version_hashes_leave_out_the_material_and_requirement_judges() -> (
    None
):
    hashed = {path for path in DEPENDENCIES.files if path.startswith("cad/scorecard/")}
    assert hashed == {
        "cad/scorecard/__init__.py",
        "cad/scorecard/model.py",
        "cad/scorecard/score.py",
        "cad/scorecard/waiting.py",
    }
