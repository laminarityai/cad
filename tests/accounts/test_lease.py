from pathlib import Path

import pytest

from cad.accounts.lease import LeaseHeld, take


def test_a_second_holder_of_the_data_root_is_refused(tmp_path: Path) -> None:
    held = take(tmp_path)
    with pytest.raises(LeaseHeld, match=r"held by pid \d+"):
        take(tmp_path)
    held.close()
    take(tmp_path).close()
