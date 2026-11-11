from pathlib import Path

from cad.chat.key_file import load_key

KEY = "ANTHROPIC_API_KEY"


def test_the_key_file_fills_a_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "anthropic.env"
    path.write_text(f"{KEY}=sk-from-file\n")
    environ: dict[str, str] = {}
    assert load_key(environ, path) is None
    assert environ == {KEY: "sk-from-file"}


def test_a_key_already_in_the_environment_wins(tmp_path: Path) -> None:
    path = tmp_path / "anthropic.env"
    path.write_text(f"{KEY}=sk-from-file\n")
    environ = {KEY: "sk-from-shell"}
    assert load_key(environ, path) is None
    assert environ == {KEY: "sk-from-shell"}


def test_no_key_anywhere_says_where_to_put_it_without_a_key(tmp_path: Path) -> None:
    path = tmp_path / "anthropic.env"
    environ: dict[str, str] = {}
    said = load_key(environ, path)
    assert said is not None and str(path) in said
    assert environ == {}
