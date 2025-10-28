from collections.abc import Sequence
from typing import Any


def flatten_dict(d: dict[str, Any], prefix: str, skip_none: bool) -> dict[str, str]:
    mapped = {}
    key_prefix = f"{prefix}-" if prefix else ""

    for k, v in d.items():
        mapped.update(_map_field_to_dict(key_prefix + k, v, skip_none))

    return mapped


def _map_field_to_dict(k: str, v: Any, skip_none: bool = False) -> dict[str, str]:
    mapped = {}
    match v:
        case None:
            if not skip_none:
                mapped[k] = ""
        case str():
            mapped[k] = v
        case Sequence():
            items = tuple(item for item in v if item is not None) if skip_none else v
            mapped.update(_map_sequence_to_dict(items, k, skip_none))
        case dict():
            mapped.update(flatten_dict(v, k, skip_none))
        case _:
            mapped[k] = str(v)
    return mapped


def _map_sequence_to_dict(items: Sequence[Any], field_name: str, skip_none: bool) -> dict[str, str]:
    mapped = {}
    mapped[_len_key(field_name)] = str(len(items))
    for idx, item in enumerate(items, start=1):
        mapped.update(_map_field_to_dict(f"{field_name}-{idx}", item, skip_none))

    return mapped


def _len_key(k: str) -> str:
    last_dash = k.rfind("-")
    if last_dash != -1:
        len_k = k[:last_dash] + "-#" + k[last_dash:]
    else:
        len_k = "#-" + k

    return len_k
