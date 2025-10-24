import types
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar, Union, get_args, get_origin

import pydantic
from pydantic.fields import FieldInfo

M = TypeVar("M", bound=pydantic.BaseModel)


def map_to_model(model: type[M], data: dict[str, Any], prefix: str = "") -> M:
    if prefix:
        strip = prefix + "-"
        data = {k.removeprefix(strip): v for k, v in data.items()}
    else:
        data = data.copy()

    fields = model.model_fields
    sequence_fields, mapping_fields, model_fields = _get_fields_by_type(fields)

    keys_to_remove = _process_sequence_fields(data, sequence_fields)
    _remove_keys_from_data(data, keys_to_remove)

    keys_to_remove = _process_model_fields(data, fields, model_fields)
    _remove_keys_from_data(data, keys_to_remove)

    keys_to_remove = _process_mapping_fields(data, mapping_fields)
    _remove_keys_from_data(data, keys_to_remove)

    return model(**data)


def _remove_keys_from_data(data: dict[str, Any], keys: set[str]) -> None:
    for key in keys:
        if key in data:
            del data[key]


def _get_fields_by_type(
    fields: dict[str, FieldInfo],
) -> tuple[set[str], set[str], set[str]]:
    sequence_fields = set()
    mapping_fields = set()
    model_fields = set()

    for field_name, info in fields.items():
        if info.annotation is None:
            continue
        if _is_sequence_field(info.annotation):
            sequence_fields.add(field_name)
        if _is_dict(info.annotation):
            mapping_fields.add(field_name)
        if _is_pydantic_model(info.annotation):
            model_fields.add(field_name)

    return sequence_fields, mapping_fields, model_fields


def _process_sequence_fields(data: dict[str, Any], sequence_fields: set[str]) -> set[str]:
    remove_keys = set()
    for field_name in sequence_fields:
        if field_name in data:
            continue

        counter_key = f"#-{field_name}"
        if counter_key not in data:
            continue

        remove_keys.add(counter_key)
        number_of_fields = int(data[counter_key])
        field_values = []
        for i in range(1, number_of_fields + 1):
            field_key = f"{field_name}-{i}"
            field_value = data[field_key]
            field_values.append(field_value)
            remove_keys.add(field_key)

        data[field_name] = field_values

    return remove_keys


def _process_model_fields(
    data: dict[str, Any], fields: dict[str, FieldInfo], model_fields: set[str]
) -> set[str]:
    remove_keys: set[str] = set()
    for field_name in model_fields:
        if field_name in data:
            continue

        field_info = fields[field_name]

        possible_models = _get_all_model_types(field_info.annotation)
        if not possible_models:
            continue

        nested_prefix = field_name + "-"
        nested_data = {k: v for k, v in data.items() if k.startswith(nested_prefix)}

        if not nested_data:
            continue

        for nested_model_type in possible_models:
            if _keys_match_model_fields(nested_model_type, nested_data, nested_prefix):
                data[field_name] = map_to_model(nested_model_type, nested_data, prefix=field_name)
                remove_keys.update(nested_data.keys())
                break

    return remove_keys


def _process_mapping_fields(data: dict[str, Any], mapping_fields: set[str]) -> set[str]:
    remove_keys = set()
    for field_name in mapping_fields:
        if field_name in data:
            continue

        mapping_prefix = field_name + "-"
        data[field_name] = {}
        for k, v in data.items():
            if not k.startswith(mapping_prefix):
                continue

            new_key = k.removeprefix(mapping_prefix)
            data[field_name][new_key] = v
            remove_keys.add(k)

    return remove_keys


def _check_annotation_with_union(annotation: Any, check_func: Callable[[Any], bool]) -> bool:
    if _is_union(annotation):
        return any(check_func(arg) for arg in get_args(annotation))
    return False


def _is_dict(annotation: Any) -> bool:
    if _is_union(annotation):
        return _check_annotation_with_union(annotation, _is_dict)

    origin = get_origin(annotation) or annotation
    try:
        return origin is dict or issubclass(origin, Mapping)
    except TypeError:
        return False


def _is_sequence_field(annotation: Any) -> bool:
    if _is_union(annotation):
        return _check_annotation_with_union(annotation, _is_sequence_field)

    origin = get_origin(annotation) or annotation

    if origin in (list, tuple):
        return True

    try:
        return issubclass(origin, Sequence) and origin is not str
    except TypeError:
        return False


def _is_pydantic_model(annotation: Any) -> bool:
    if _is_union(annotation):
        return _check_annotation_with_union(annotation, _is_pydantic_model)

    origin = get_origin(annotation) or annotation
    try:
        return issubclass(origin, pydantic.BaseModel)
    except TypeError:
        return False


def _is_union(annotation: Any) -> bool:
    return get_origin(annotation) in (Union, getattr(types, "UnionType", None))


def _keys_match_model_fields(
    model: type[pydantic.BaseModel], data: dict[str, Any], prefix: str
) -> bool:
    """Check if data keys match the model's field structure after prefix removal."""
    model_fields = model.model_fields

    for key in data.keys():
        stripped = key.removeprefix(prefix)

        # Check if stripped key matches or relates to any model field
        matched = False
        for field_name in model_fields.keys():
            if (
                stripped == field_name
                or stripped.startswith(field_name + "-")
                or stripped == f"#-{field_name}"
            ):
                matched = True
                break

        if not matched:
            return False  # Found a key that doesn't match any field

    return True  # All keys match model fields


def _get_all_model_types(annotation: Any) -> list[type[pydantic.BaseModel]]:
    """Extract all Pydantic model types from an annotation (including unions)."""
    if _is_union(annotation):
        models: list[type[pydantic.BaseModel]] = []
        for arg in get_args(annotation):
            models.extend(_get_all_model_types(arg))
        return models

    try:
        if issubclass(annotation, pydantic.BaseModel):
            return [annotation]
    except TypeError:
        pass

    return []
