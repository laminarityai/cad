"""The scripted agent for the in-process driver: the steps a careful agent takes up to an Auto stop.

It reads the requirements a brief's grader names and plays them as the agent's proposal, so the
run is as deterministic as the model double. It builds nothing: after `auto_start` it asks for
the person, so a brief whose requirements agree stops with `agent_asked`, and one whose
requirements conflict is stopped by the server before the call returns.
"""

from typing import Any, Final, cast

from brief_set import BriefInput

from cad.chat.scripted import Call, Script, Step

DEFAULT_MATERIAL: Final = "prusament-pla"
TABLE_KEY: Final = "not-in-table"
NOTE: Final = "The scripted agent builds nothing, so the person decides what comes next."


def script_for(brief: BriefInput) -> Script:
    requirements = [_requirement(one) for one in _grader_requirements(brief)]
    steps = (
        Step(
            text="Storing the brief.",
            calls=(Call(name="create_brief", input={"text": brief.text}),),
        ),
        Step(
            text="Proposing requirements.",
            calls=(
                Call(
                    name="propose_requirements",
                    input={"brief_id": "${create_brief.brief_id}", "requirements": requirements},
                ),
            ),
        ),
        Step(
            text="Asking you to confirm.",
            calls=(
                Call(name="ask_to_confirm", input={"project_id": "${create_brief.project_id}"}),
            ),
        ),
        Step(
            text="Starting the run.",
            calls=(
                Call(
                    name="auto_start",
                    input={
                        "brief_id": "${create_brief.brief_id}",
                        "material_key": _material_key(brief),
                        "material_reason": "the scripted run's stand-in material",
                    },
                ),
            ),
        ),
        Step(
            text="Asking for you.",
            calls=(Call(name="auto_ask", input={"run_id": "${auto_start.run_id}", "note": NOTE}),),
        ),
    )
    return Script(steps=steps)


def _grader_requirements(brief: BriefInput) -> list[dict[str, Any]]:
    found = brief.grader.get("requirements")
    return cast("list[dict[str, Any]]", found) if isinstance(found, list) else []


def _material_key(brief: BriefInput) -> str:
    """The material the brief pins, because the server refuses any other, then the grader's."""
    pinned = [one["material"] for one in _grader_requirements(brief) if one["kind"] == "made_of"]
    stated = str(pinned[0] if pinned else brief.grader.get("material", ""))
    if not stated or stated == "none-stated" or stated.startswith(TABLE_KEY):
        return DEFAULT_MATERIAL
    return stated


def _requirement(grader: dict[str, Any]) -> dict[str, Any]:
    return {"target": _target(grader), "quote": grader["quote"]}


def _target(grader: dict[str, Any]) -> dict[str, Any]:
    kind, number, unit = grader["kind"], grader.get("target"), grader.get("unit")
    edges = cast("list[Any]", number) if kind == "envelope" else []
    match kind:
        case "closed_solid":
            return {"kind": kind}
        case "max_mass" | "min_mass":
            return {"kind": kind, "mass": {"magnitude": number, "unit": unit}}
        case "envelope":
            return {
                "kind": kind,
                "edges": [{"magnitude": edge, "unit": unit} for edge in edges],
            }
        case "made_of":
            return {"kind": kind, "material": grader["material"]}
        case "unchecked":
            return {"kind": kind, "statement": grader["statement"]}
        case _:
            raise ValueError(f"the scripted agent cannot propose a {kind} requirement")
