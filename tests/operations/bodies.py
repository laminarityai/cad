"""Check a body the app sent against the OpenAPI document strictly: every required field is
present, an optional one may be absent, and no field the document does not name is there."""

from typing import Final, cast

from jsonschema import Draft202012Validator, validate

from cad.operations.openapi import Json, document
from cad.operations.outside import every_route


def _strict(node: object) -> object:
    if isinstance(node, dict):
        made = {key: _strict(value) for key, value in cast(Json, node).items()}
        if isinstance(made.get("properties"), dict):
            made.setdefault("additionalProperties", False)
        return made
    if isinstance(node, list):
        return [_strict(one) for one in cast(list[object], node)]
    return node


STRICT: Final = cast(Json, _strict(document(every_route())))
COMPONENTS: Final = cast(Json, STRICT["components"])


def check(method: str, path: str, status: int, body: object) -> None:
    paths = cast(dict[str, dict[str, Json]], STRICT["paths"])
    response = cast(Json, cast(Json, paths[path][method.lower()]["responses"])[str(status)])
    ref = response.get("$ref")
    if isinstance(ref, str):
        named = cast(Json, COMPONENTS["responses"])
        response = cast(Json, named[ref.removeprefix("#/components/responses/")])
    (media,) = cast(dict[str, Json], response["content"]).values()
    schema = {**cast(Json, media["schema"]), "components": COMPONENTS}
    validate(body, schema, Draft202012Validator)
