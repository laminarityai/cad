"""The kinds of target a requirement can state."""

from enum import StrEnum


class Kind(StrEnum):
    CLOSED_SOLID = "closed_solid"
    MAX_MASS = "max_mass"
    MIN_MASS = "min_mass"
    ENVELOPE = "envelope"
    MEASURE_LIMIT = "measure_limit"
    UNCHECKED = "unchecked"
    MADE_OF = "made_of"
    MIN_SAFETY_FACTOR = "min_safety_factor"
    MAX_DEFLECTION = "max_deflection"
    MIN_CLEARANCE = "min_clearance"
    MAX_CLEARANCE = "max_clearance"
    FASTENER_HOLES = "fastener_holes"
    PLAIN_HOLES = "plain_holes"
    FITS_WITH = "fits_with"
    AGENT_LIMIT = "agent_limit"
