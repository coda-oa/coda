import types
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Union, get_args, get_origin

import pydantic

from ._keys import KeyMatcher

_key_matcher = KeyMatcher()


def with_union_support(type_checker_func: Callable[[Any], bool]) -> Callable[[Any], bool]:
    """Decorator to automatically handle union types in type checkers."""

    def wrapper(annotation: Any) -> bool:
        if is_union(annotation):
            return any(type_checker_func(arg) for arg in get_args(annotation))
        return type_checker_func(annotation)

    return wrapper


@with_union_support
def is_dict(annotation: Any) -> bool:
    origin = get_origin(annotation) or annotation
    try:
        return origin is dict or issubclass(origin, Mapping)
    except TypeError:
        return False


@with_union_support
def is_sequence_field(annotation: Any) -> bool:
    origin = get_origin(annotation) or annotation

    if origin in (list, tuple):
        return True

    try:
        return issubclass(origin, Sequence) and origin is not str
    except TypeError:
        return False


@with_union_support
def is_pydantic_model(annotation: Any) -> bool:
    origin = get_origin(annotation) or annotation
    try:
        return issubclass(origin, pydantic.BaseModel)
    except TypeError:
        return False


def is_union(annotation: Any) -> bool:
    return get_origin(annotation) in (Union, getattr(types, "UnionType", None))


def get_matching_model_type(
    candidates: list[type[pydantic.BaseModel]], data: dict[str, Any], prefix: str
) -> type[pydantic.BaseModel] | None:
    for c in candidates:
        if _keys_match_model_fields(c, data, prefix):
            return c

    return None


def get_all_model_types(annotation: Any) -> list[type[pydantic.BaseModel]]:
    """Extract all Pydantic model types from an annotation (including unions)."""
    if is_union(annotation):
        models: list[type[pydantic.BaseModel]] = []
        for arg in get_args(annotation):
            models.extend(get_all_model_types(arg))
        return models

    try:
        if issubclass(annotation, pydantic.BaseModel):
            return [annotation]
    except TypeError:
        pass

    return []


def _keys_match_model_fields(
    model: type[pydantic.BaseModel], data: dict[str, Any], prefix: str
) -> bool:
    """Check if data keys match the model's field structure after prefix removal."""
    model_fields = model.model_fields

    for key in data.keys():
        stripped = key.removeprefix(prefix)

        matched = False
        for field_name in model_fields.keys():
            if _key_matcher.matches_field_pattern(stripped, field_name):
                matched = True
                break

        if not matched:
            return False

    return True
