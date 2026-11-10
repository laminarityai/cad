import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, TypeAliasType, cast

from pydantic import BaseModel, TypeAdapter
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaMode
from pydantic_core import CoreSchema, core_schema

from cad.operations.model import Audience, Operation
from cad.operations.routes import Served

type Json = dict[str, object]

SCHEMAS: Final = "#/components/schemas/"
REF: Final = SCHEMAS + "{model}"
ERROR: Final = "Error"
FAILURES: Final = {
    400: ("Refused", "the server refused the request"),
    401: ("SignedOut", "no signed-in person: send a Clerk session token"),
    404: ("NotFound", "the named variant, brief, project or conversation is not stored"),
    409: ("Busy", "the agent is still answering the last message"),
    415: ("NotJson", "the request is not application/json"),
    422: ("Malformed", "an argument is missing, unknown or malformed"),
    503: ("Unavailable", "a service the call needs is not available"),
}


class Untitled(GenerateJsonSchema):
    def field_title_should_be_set(self, schema: object) -> bool:
        del schema
        return False

    def field_is_required(
        self,
        field: core_schema.ModelField | core_schema.DataclassField | core_schema.TypedDictField,
        total: bool,
    ) -> bool:
        """A body the server sends holds every field, defaulted or not, except one whose
        `exclude_if` held, which may be absent."""
        if self.mode == "serialization":
            return field.get("serialization_exclude_if") is None
        return super().field_is_required(field, total)


REGISTRY_FAILURES: Final = (400, 401, 404, 422, 503)


@dataclass(frozen=True, slots=True)
class Described:
    name: str
    path: str
    method: str
    input: type[BaseModel]
    output: type[BaseModel] | TypeAliasType
    immutable: bool = False
    status: int = 200
    events: str = ""
    requires_json_body: bool = False
    failures: tuple[int, ...] = REGISTRY_FAILURES


def from_registry(operations: Iterable[Operation], routes: Mapping[str, Served]) -> list[Described]:
    reachable = [one for one in operations if Audience.PERSON in one.audience]
    if {one.name for one in reachable} != set(routes):
        raise ValueError("the routes table and the person operations differ")
    return [
        Described(
            name=one.name,
            path=routes[one.name].path,
            method=routes[one.name].method,
            input=one.input,
            output=one.output,
            immutable=routes[one.name].immutable,
        )
        for one in reachable
    ]


def document(described: Sequence[Described]) -> Json:
    generator = Untitled(ref_template=REF)
    wanted: list[tuple[str, JsonSchemaMode, CoreSchema]] = []
    for one in described:
        wanted.append((one.name, "validation", TypeAdapter(one.input).core_schema))
        wanted.append(
            (
                one.name,
                "serialization",
                TypeAdapter[object](cast(type[object], one.output)).core_schema,
            )
        )
    made, definitions = generator.generate_definitions(wanted)
    schemas = {**definitions, ERROR: _error_schema()}
    paths: dict[str, Json] = {}
    for one in described:
        item = paths.setdefault(one.path, {})
        item[one.method.lower()] = _operation(
            one,
            _input_fields(made[(one.name, "validation")], schemas),
            made[(one.name, "serialization")],
        )
    used = _schemas_named_by(paths, schemas) | {ERROR}
    return {
        "openapi": "3.1.0",
        "info": {"title": "cad", "version": "v1"},
        "security": [{"session": []}, {"bearer": []}],
        "paths": paths,
        "components": {
            "schemas": {name: schemas[name] for name in sorted(used)},
            "responses": {
                name: {
                    "description": why,
                    "content": {"application/json": {"schema": {"$ref": REF.format(model=ERROR)}}},
                }
                for name, why in FAILURES.values()
            },
            "securitySchemes": {
                "session": {"type": "apiKey", "in": "cookie", "name": "__session"},
                "bearer": {"type": "http", "scheme": "bearer"},
            },
        },
    }


def _schemas_named_by(paths: Mapping[str, object], schemas: Mapping[str, object]) -> set[str]:
    found: set[str] = set()
    pending: list[object] = [paths]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            for key, value in cast(Json, node).items():
                if key == "$ref" and isinstance(value, str):
                    if not value.startswith(SCHEMAS):
                        continue
                    name = value.removeprefix(SCHEMAS)
                    if name not in found:
                        found.add(name)
                        pending.append(schemas[name])
                else:
                    pending.append(value)
        elif isinstance(node, list):
            pending.extend(cast(list[object], node))
    return found


def _error_schema() -> Json:
    return {
        "type": "object",
        "properties": {"error": {"type": "string"}},
        "required": ["error"],
        "additionalProperties": False,
    }


def _input_fields(schema: Json, schemas: Mapping[str, object]) -> Json:
    ref = schema.get("$ref")
    if isinstance(ref, str):
        schema = cast(Json, schemas[ref.removeprefix(SCHEMAS)])
    return schema


def _operation(one: Described, fields: Json, output: Json) -> Json:
    properties = cast(dict[str, Json], fields.get("properties", {}))
    required = set(cast(list[str], fields.get("required", [])))
    templated = set(re.findall(r"{(\w+)}", one.path))
    if not templated <= set(properties):
        raise ValueError(f"{one.path} names {sorted(templated - set(properties))}, no argument")
    parameters = [_parameter(name, "path", True, properties[name]) for name in sorted(templated)]
    result: Json = {"operationId": one.name}
    rest = [name for name in properties if name not in templated]
    if one.method == "GET":
        parameters += [
            _parameter(name, "query", name in required, properties[name]) for name in rest
        ]
    elif rest or one.requires_json_body:
        result["requestBody"] = {
            "required": bool(required - templated) or one.requires_json_body,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {name: properties[name] for name in rest},
                        "required": sorted(required - templated),
                        "additionalProperties": False,
                    }
                }
            },
        }
    if parameters:
        result["parameters"] = parameters
    result["responses"] = _responses(one, output)
    return result


def _parameter(name: str, where: str, required: bool, schema: Json) -> Json:
    return {"name": name, "in": where, "required": required, "schema": schema}


def _responses(one: Described, output: Json) -> Json:
    media = "text/event-stream" if one.events else "application/json"
    ok: Json = {"description": one.events or "the result", "content": {media: {"schema": output}}}
    responses: Json = {str(one.status): ok}
    if one.immutable:
        ok["headers"] = {
            "ETag": {"schema": {"type": "string"}},
            "Cache-Control": {"schema": {"type": "string"}},
        }
        responses["304"] = {"description": "the client's copy, named by If-None-Match, is current"}
    for status in one.failures:
        responses[str(status)] = {"$ref": f"#/components/responses/{FAILURES[status][0]}"}
    return dict(sorted(responses.items()))
