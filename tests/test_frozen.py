import importlib
import inspect
import pkgutil

from pydantic import BaseModel

import cad
from cad.frozen import Frozen


def models() -> set[type[BaseModel]]:
    found: set[type[BaseModel]] = set()
    for info in pkgutil.walk_packages(cad.__path__, "cad."):
        if info.name.endswith(".__main__"):
            continue
        module = importlib.import_module(info.name)
        for _, value in inspect.getmembers(module, inspect.isclass):
            if issubclass(value, BaseModel) and value.__module__ == info.name:
                found.add(value)
    return found


def test_a_frozen_model_that_refuses_extra_fields_derives_from_the_one_base() -> None:
    """`Frozen` is the one way to say it. A model that spells the same config itself is a second
    way, and it hides from a later change to the base."""
    own_spelling = [
        f"{model.__module__}.{model.__qualname__}"
        for model in models()
        if model is not Frozen
        and not issubclass(model, Frozen)
        and model.model_config.get("frozen") is True
        and model.model_config.get("extra") == "forbid"
    ]
    assert sorted(own_spelling) == []
