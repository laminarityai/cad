"""The one build script that runs every agent measurement of a call against the scored shape.

The script runs through the unchanged build sandbox. Each snippet runs in a fresh namespace that
holds the build123d names, `part` and `report`. Every line the host reads starts with `MARK`. The
mark holds no character that `str.splitlines` splits on, such as `\\x1e`.
"""

import base64
from collections.abc import Sequence
from typing import Final

MARK: Final = "@@cad-measure "

PREAMBLE: Final = """
import base64 as _base64, json as _json
from build123d import *
_NAMES = {{_k: _v for _k, _v in dict(globals()).items() if not _k.startswith("_")}}
with open("/tmp/part.brep", "wb") as _file:
    _file.write(_base64.b64decode({brep!r}))
_PART = import_brep("/tmp/part.brep")

def _say(**fields):
    print("\\n" + {mark!r} + _json.dumps(fields), flush=True)

def _reporter(slot):
    def report(name, value, unit):
        _say(slot=slot, name=str(name), value=float(value), unit=str(unit))
    return report

def _measure(slot, code):
    try:
        exec(compile(code, f"<measurement {{slot}}>", "exec"),
             {{**_NAMES, "part": _PART, "report": _reporter(slot)}})
    except BaseException as _error:
        _say(slot=slot, failed=repr(_error)[:300])
    else:
        _say(slot=slot, done=True)
"""


def compose(brep: bytes, codes: Sequence[str]) -> str:
    """`result` is a point, so the build report stays tiny whatever the snippets did."""
    head = PREAMBLE.format(brep=base64.b64encode(brep).decode(), mark=MARK)
    body = "".join(f"_measure({slot}, {code!r})\n" for slot, code in enumerate(codes))
    return head + body + "result = Vertex(0, 0, 0)\n"
