"""The parts a person supplied that a variant's build read (ADR-0012). No check grades them.

Every check version hashes this file, so it imports nothing from the project store: the
operations layer reads each part's name and origin and passes them in."""

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import Field

from cad.frozen import Frozen
from cad.sandbox.outcome import PartPlacement, PartUse


class Uploaded(Frozen):
    """The person added the part's file. The account and session that sent it stay off the card."""

    kind: Literal["upload"] = "upload"
    file_name: str


class FromOption(Frozen):
    """The person confirmed an option the agent built as the part."""

    kind: Literal["variant"] = "variant"
    variant_id: str


type SuppliedOrigin = Annotated[Uploaded | FromOption, Field(discriminator="kind")]


class Named(Frozen):
    """What the project's confirmed record of a part says it is."""

    name: str
    origin: SuppliedOrigin


class SuppliedPart(Named):
    """One part the build read. `part_id`, `brep_sha256` and `placements` are the variant's signed
    build record: the BREP the build was sent and each copy it placed, none when it only read the
    part. `name` and `origin` are the project's confirmed record of the part. The card's own
    `brep_sha256` is the body the agent made, and only that body is graded."""

    part_id: str
    brep_sha256: str
    placements: tuple[PartPlacement, ...] = ()


def supplied(uses: Sequence[PartUse], named: Mapping[str, Named]) -> tuple[SuppliedPart, ...]:
    """A row for each part a build read, in the order its record lists them. `named` must name
    every part in `uses`."""
    return tuple(
        SuppliedPart(
            part_id=use.part_id,
            name=named[use.part_id].name,
            origin=named[use.part_id].origin,
            brep_sha256=use.brep_sha256,
            placements=use.placements,
        )
        for use in uses
    )
