from collections.abc import Sequence
from typing import Any, TypeVar

import pydantic
from ._keys import KeyMatcher


MAX_SEQUENCE_LENGTH = 10000

M = TypeVar("M", bound=pydantic.BaseModel)


def map_to_model(model: type[M], data: dict[str, Any], prefix: str = "") -> M:
    from ._processors import (
        ProcessorChain,
        SequenceFieldProcessor,
        ModelFieldProcessor,
        MappingFieldProcessor,
    )

    key_matcher = KeyMatcher()
    input_data = key_matcher.strip_prefix(data, prefix)

    processor_chain = ProcessorChain(
        [
            SequenceFieldProcessor(MAX_SEQUENCE_LENGTH),
            ModelFieldProcessor(),
            MappingFieldProcessor(),
        ]
    )

    processed_data = processor_chain.process_all_fields(input_data, model.model_fields, model=model)

    return model(**processed_data)


def map_to_dict(obj: pydantic.BaseModel) -> dict[str, str]:
    dump = obj.model_dump()
    mapped: dict[str, str] = {}
    for k, v in dump.items():
        mapped.update(_map_field_to_dict(k, v))

    return mapped


def _map_field_to_dict(k: str, v: Any) -> dict[str, str]:
    mapped = {}
    match v:
        case str():
            mapped[k] = str(v)
        case Sequence():
            last_dash = k.rfind("-")
            if last_dash != -1:
                len_k = k[:last_dash] + "-#" + k[last_dash:]
            else:
                len_k = "#-" + k
            mapped[len_k] = str(len(v))
            for i, item in enumerate(v, start=1):
                mapped.update(_map_field_to_dict(f"{k}-{i}", item))
        case dict():
            for sub_k, sub_v in v.items():
                mapped.update(_map_field_to_dict(f"{k}-{sub_k}", sub_v))
        case _:
            mapped[k] = str(v)
    return mapped
