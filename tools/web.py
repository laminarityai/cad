"""Run one of the web page's npm scripts: `lint`, `test` or `build`. These are the `web lint`,
`web test` and `web build` steps of `uv run verify`. The page's packages are installed first when
`web/package-lock.json` is newer than `web/node_modules`.
"""

import shutil
import subprocess
import sys

from gen_ts import WEB, install_if_stale

SCRIPTS = ("lint", "test", "build")
NO_NODE = (
    "web: node and npm are not on PATH, and the web steps need them. "
    "Install Node 22 or later (macOS: brew install node), then run it again."
)


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in SCRIPTS:
        print(f"usage: web.py {'|'.join(SCRIPTS)}")
        return 2
    if shutil.which("node") is None or shutil.which("npm") is None:
        print(NO_NODE)
        return 1
    install_if_stale()
    return subprocess.run(["npm", "run", "--silent", argv[0]], cwd=WEB, check=False).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
