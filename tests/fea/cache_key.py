"""The inputs every cached solve report shares, and the key CI saves the report cache under.

Run as a script, it prints a digest of the images and these shared inputs. A report's own key in
test_hand_calcs.py adds what differs per case, so CI restores only reports a run can use.
"""

import hashlib
from pathlib import Path
from typing import Final

from cad.sandbox import container
from cad.sandbox.image import IMAGES, current_image, image_tag
from cad.sandbox.stage import read_sources

CORE: Final = read_sources("cad.checks.container.fea")
HARNESS: Final = Path(__file__).parent


def shared_inputs() -> str:
    """Digest the solver sources, container.py (it holds the docker flags) and the harness.

    The harness enters by content, without `__pycache__`.
    """
    digest = hashlib.sha256(CORE.digest.encode())
    digest.update(hashlib.sha256(Path(container.__file__).read_bytes()).digest())
    for path in sorted(HARNESS.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.relative_to(HARNESS).as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


if __name__ == "__main__":
    images = " ".join(current_image(image_tag(image)) for image in IMAGES)
    print(hashlib.sha256(f"{images} {shared_inputs()}".encode()).hexdigest()[:32])
