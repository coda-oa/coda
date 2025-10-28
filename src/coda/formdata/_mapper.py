from typing import Any, TypeVar

import pydantic

from ._keys import KeyMatcher
from ._to_dict import flatten_dict

MAX_SEQUENCE_LENGTH = 10000

M = TypeVar("M", bound=pydantic.BaseModel)


def map_to_model(model: type[M], data: dict[str, Any], prefix: str = "") -> M:
    from ._processors import (
        MappingFieldProcessor,
        ModelFieldProcessor,
        ProcessorChain,
        SequenceFieldProcessor,
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


def map_to_dict(
    obj: pydantic.BaseModel, *, prefix: str = "", skip_none: bool = False
) -> dict[str, str]:
    return flatten_dict(obj.model_dump(mode="json"), prefix=prefix, skip_none=skip_none)
