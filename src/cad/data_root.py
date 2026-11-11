"""Every store's default directory. It imports nothing from cad, so any package can derive its
root from it."""

from pathlib import Path
from typing import Final

DATA_ROOT: Final = Path.home() / ".cad"
