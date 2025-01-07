from typing import Annotated, Any, TypeVar

from pydantic import BaseModel, BeforeValidator
from pydantic_core import to_jsonable_python

TOption = TypeVar("TOption")


def empty_str_as_none(value: str | None) -> str | None:
    return None if value == "" else value


OptionalFromStr = Annotated[TOption | None, BeforeValidator(empty_str_as_none)]


def to_post_data(
    model: BaseModel,
    *,
    prefix: str = "",
    exclude: set[str] | None = None,
    underscores_to_dash: bool = False,
) -> dict[str, Any]:
    return {
        _build_key(k, prefix, underscores_to_dash): _to_json(v)
        for k, v in model.model_dump(mode="json", exclude=exclude).items()
    }


def _build_key(key: str, prefix: str = "", underscores_to_dash: bool = False) -> str:
    if prefix:
        prefix = f"{prefix}-"

    key = prefix + key
    if underscores_to_dash:
        key = key.replace("_", "-")

    return key


def _to_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return to_post_data(value)

    if isinstance(value, dict):
        value = {k: v if v is not None else "" for k, v in value.items()}

    serialized: Any
    if value is None:
        serialized = ""
    else:
        serialized = to_jsonable_python(value)

    return serialized


class CodaBaseDto(BaseModel):
    def to_post_data(
        self,
        *,
        prefix: str = "",
        exclude: set[str] | None = None,
        underscores_to_dash: bool = False,
    ) -> dict[str, Any]:
        return to_post_data(
            self, prefix=prefix, exclude=exclude, underscores_to_dash=underscores_to_dash
        )
