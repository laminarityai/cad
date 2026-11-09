from typing import Final, NewType

ContextPartId = NewType("ContextPartId", str)
PART_ID_PATTERN: Final = r"^part-[0-9a-f]{16}$"


def part_id(brep_sha256: str) -> ContextPartId:
    return ContextPartId(f"part-{brep_sha256[:16]}")
