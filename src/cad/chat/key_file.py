"""The Anthropic key file cad-http reads on start, so a plain `uv run cad-http` has the key.

The file holds one line, `ANTHROPIC_API_KEY=...`. A key already in the environment wins. The key
is never printed or logged.
"""

from collections.abc import MutableMapping
from pathlib import Path
from typing import Final

from cad.chat.anthropic_model import KEY_VARIABLE

KEY_FILE: Final = Path.home() / ".config" / "cad" / "anthropic.env"


def load_key(environ: MutableMapping[str, str], path: Path = KEY_FILE) -> str | None:
    """Sets the key in `environ` from `path` when `environ` lacks it. Returns a line to print when
    neither has it, or None."""
    if environ.get(KEY_VARIABLE, "").strip():
        return None
    if path.is_file():
        for line in path.read_text().splitlines():
            name, _, value = line.removeprefix("export ").partition("=")
            value = value.strip().strip("'\"")
            if name.strip() == KEY_VARIABLE and value:
                environ[KEY_VARIABLE] = value
                return None
    return (
        f"cad-http: no {KEY_VARIABLE}, so the chat cannot run; put {KEY_VARIABLE}=<key> in {path}"
    )
