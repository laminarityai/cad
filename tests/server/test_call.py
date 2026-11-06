import pytest

from cad.server import call


@pytest.mark.parametrize("arguments", ["{not json", "", "[1, 2]", "3"])
def test_arguments_that_are_not_a_json_object_exit_2_without_a_traceback(
    arguments: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        call.main(["server_info", arguments])
    assert raised.value.code == 2
    assert "Traceback" not in capsys.readouterr().err
