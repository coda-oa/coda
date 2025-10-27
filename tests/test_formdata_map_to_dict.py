import pydantic
import pytest

from coda import formdata


class OneField(pydantic.BaseModel):
    a_str: str


def test__can_map_simple_data_to_dict() -> None:
    data = OneField(a_str="some-value")

    actual = formdata.map_to_dict(data)

    expected = {"a_str": "some-value"}

    assert actual == expected


class ListField(pydantic.BaseModel):
    a_seq: list[int]


class TupleField(pydantic.BaseModel):
    a_seq: tuple[int, int, int]


@pytest.mark.parametrize("data", (ListField(a_seq=[1, 2, 3]), TupleField(a_seq=(1, 2, 3))))
def test__sequence_field__gets_mapped_with_counter(data: ListField | TupleField) -> None:
    actual = formdata.map_to_dict(data)

    expected = {
        "#-a_seq": "3",
        "a_seq-1": "1",
        "a_seq-2": "2",
        "a_seq-3": "3",
    }
    assert actual == expected


class DictField(pydantic.BaseModel):
    a_dict: dict[str, int]


def test__dict_field__keys_are_mapped_as_individual_fields() -> None:
    data = DictField(a_dict={"first": 1, "second": 2, "third": 3})

    actual = formdata.map_to_dict(data)

    expected = {
        "a_dict-first": "1",
        "a_dict-second": "2",
        "a_dict-third": "3",
    }

    assert actual == expected


class ModelField(pydantic.BaseModel):
    nested: OneField


def test__model_field__gets_fields_mapped_as_individual_fields() -> None:
    data = ModelField(nested=OneField(a_str="some-value"))

    actual = formdata.map_to_dict(data)

    expected = {"nested-a_str": "some-value"}

    assert actual == expected


class NestedModelWithList(pydantic.BaseModel):
    nested: ListField


def test__model_field_with_nested_list_field__chains_list_keys_to_model_field() -> None:
    data = NestedModelWithList(nested=ListField(a_seq=[1, 2, 3]))

    actual = formdata.map_to_dict(data)

    expected = {
        "nested-#-a_seq": "3",
        "nested-a_seq-1": "1",
        "nested-a_seq-2": "2",
        "nested-a_seq-3": "3",
    }

    assert actual == expected


class NestedModelWithDict(pydantic.BaseModel):
    nested: DictField


def test__model_field_with_nested_dict_field__chains_dict_keys_to_model_field() -> None:
    data = NestedModelWithDict(nested=DictField(a_dict={"first": 1, "second": 2}))

    actual = formdata.map_to_dict(data)

    expected = {
        "nested-a_dict-first": "1",
        "nested-a_dict-second": "2",
    }

    assert actual == expected
