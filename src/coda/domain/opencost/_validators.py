from typing import Annotated, Any, ClassVar, Self

from pydantic import AfterValidator, BaseModel, model_validator


def _at_least_one_item[T](value: list[T]) -> list[T]:
    if not value:
        raise ValueError("must contain at least one item.")

    return value


type RequiredList[T] = Annotated[list[T], AfterValidator(_at_least_one_item)]


class EitherFieldMixin(BaseModel):
    """Mixin for models that require at least one of the named fields to be set.

    Must be mixed into a ``BaseModel`` subclass. Do not instantiate directly.
    """

    either_fields: ClassVar[tuple[str, ...]] = ()

    def model_post_init(self, __context: Any) -> None:
        if type(self) is EitherFieldMixin:
            raise TypeError("EitherFieldMixin must not be instantiated directly")

    @model_validator(mode="after")
    def _at_least_one_either_field(self) -> Self:
        names = type(self).either_fields
        if names and not any(getattr(self, name) for name in names):
            choices = " or ".join(f"'{name}'" for name in names)
            raise ValueError(f"at least one of {choices} must be set")
        return self
