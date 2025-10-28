import enum
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


class TheEnum(enum.Enum):
    a = "a"
    b = "b"


class EnumFieldModel(pydantic.BaseModel):
    enum: TheEnum


def test__model_with_enum_field__maps_enum_value_to_dict() -> None:
    data = EnumFieldModel(enum=TheEnum.a)

    actual = formdata.map_to_dict(data)

    expected = {"enum": "a"}

    assert actual == expected


class OptionalField(pydantic.BaseModel):
    optional_str: str | None


def test__none_field__skip_none_false__converts_to_empty_string() -> None:
    data = OptionalField(optional_str=None)

    actual = formdata.map_to_dict(data, skip_none=False)

    expected = {"optional_str": ""}
    assert actual == expected


def test__none_field__skip_none_true__omits_field() -> None:
    data = OptionalField(optional_str=None)

    actual = formdata.map_to_dict(data, skip_none=True)

    expected: dict[str, str] = {}
    assert actual == expected


def test__optional_field_with_value__skip_none_false__keeps_value() -> None:
    data = OptionalField(optional_str="some-value")

    actual = formdata.map_to_dict(data, skip_none=False)

    expected = {"optional_str": "some-value"}
    assert actual == expected


def test__optional_field_with_value__skip_none_true__keeps_value() -> None:
    data = OptionalField(optional_str="some-value")

    actual = formdata.map_to_dict(data, skip_none=True)

    expected = {"optional_str": "some-value"}
    assert actual == expected


class OptionalListField(pydantic.BaseModel):
    a_seq: list[int | None]


def test__none_in_list__skip_none_false__converts_to_empty_string() -> None:
    data = OptionalListField(a_seq=[1, None, 3])

    actual = formdata.map_to_dict(data, skip_none=False)

    expected = {
        "#-a_seq": "3",
        "a_seq-1": "1",
        "a_seq-2": "",
        "a_seq-3": "3",
    }
    assert actual == expected


def test__none_in_list__skip_none_true__reindexes_without_gaps() -> None:
    data = OptionalListField(a_seq=[1, None, 3])

    actual = formdata.map_to_dict(data, skip_none=True)

    expected = {
        "#-a_seq": "2",
        "a_seq-1": "1",
        "a_seq-2": "3",
    }
    assert actual == expected


def test__list_with_all_nones__skip_none_false__keeps_indices() -> None:
    data = OptionalListField(a_seq=[None, None, None])

    actual = formdata.map_to_dict(data, skip_none=False)

    expected = {
        "#-a_seq": "3",
        "a_seq-1": "",
        "a_seq-2": "",
        "a_seq-3": "",
    }
    assert actual == expected


def test__list_with_all_nones__skip_none_true__empty_sequence() -> None:
    data = OptionalListField(a_seq=[None, None, None])

    actual = formdata.map_to_dict(data, skip_none=True)

    expected = {"#-a_seq": "0"}
    assert actual == expected


def test__none_at_start_middle_end__skip_none_true__reindexes_correctly() -> None:
    data = OptionalListField(a_seq=[None, 2, None, 4, None])

    actual = formdata.map_to_dict(data, skip_none=True)

    expected = {
        "#-a_seq": "2",
        "a_seq-1": "2",
        "a_seq-2": "4",
    }
    assert actual == expected


class OptionalDictField(pydantic.BaseModel):
    a_dict: dict[str, int | None]


def test__none_in_dict_values__skip_none_false__converts_to_empty_string() -> None:
    data = OptionalDictField(a_dict={"first": 1, "second": None, "third": 3})

    actual = formdata.map_to_dict(data, skip_none=False)

    expected = {
        "a_dict-first": "1",
        "a_dict-second": "",
        "a_dict-third": "3",
    }
    assert actual == expected


def test__none_in_dict_values__skip_none_true__omits_keys() -> None:
    data = OptionalDictField(a_dict={"first": 1, "second": None, "third": 3})

    actual = formdata.map_to_dict(data, skip_none=True)

    expected = {
        "a_dict-first": "1",
        "a_dict-third": "3",
    }
    assert actual == expected


class NestedOptionalFields(pydantic.BaseModel):
    nested: OptionalField


def test__nested_model_with_none_fields__recursive_skip_none_false() -> None:
    data = NestedOptionalFields(nested=OptionalField(optional_str=None))

    actual = formdata.map_to_dict(data, skip_none=False)

    expected = {"nested-optional_str": ""}
    assert actual == expected


def test__nested_model_with_none_fields__recursive_skip_none_true() -> None:
    data = NestedOptionalFields(nested=OptionalField(optional_str=None))

    actual = formdata.map_to_dict(data, skip_none=True)

    expected: dict[str, str] = {}
    assert actual == expected


class InnerModel(pydantic.BaseModel):
    value: int | None


class ListOfModels(pydantic.BaseModel):
    items: list[InnerModel]


def test__list_of_models_with_none__skip_none_false() -> None:
    data = ListOfModels(items=[InnerModel(value=1), InnerModel(value=None), InnerModel(value=3)])

    actual = formdata.map_to_dict(data, skip_none=False)

    expected = {
        "#-items": "3",
        "items-1-value": "1",
        "items-2-value": "",
        "items-3-value": "3",
    }
    assert actual == expected


def test__list_of_models_with_none__skip_none_true() -> None:
    data = ListOfModels(items=[InnerModel(value=1), InnerModel(value=None), InnerModel(value=3)])

    actual = formdata.map_to_dict(data, skip_none=True)

    expected = {
        "#-items": "3",
        "items-1-value": "1",
        "items-3-value": "3",
    }
    assert actual == expected


class Level3(pydantic.BaseModel):
    value: int | None


class Level2(pydantic.BaseModel):
    level3: Level3


class Level1(pydantic.BaseModel):
    level2: Level2


class Level0(pydantic.BaseModel):
    level1: Level1


def test__deeply_nested_none__four_levels__recursive() -> None:
    data = Level0(level1=Level1(level2=Level2(level3=Level3(value=None))))

    actual_false = formdata.map_to_dict(data, skip_none=False)
    expected_false = {"level1-level2-level3-value": ""}
    assert actual_false == expected_false

    actual_true = formdata.map_to_dict(data, skip_none=True)
    expected_true: dict[str, str] = {}
    assert actual_true == expected_true


class MixedModel(pydantic.BaseModel):
    required: str
    optional: int | None
    items: list[str | None]


def test__mixed_none_and_values__both_modes() -> None:
    data = MixedModel(required="value", optional=None, items=["a", None, "c"])

    actual_false = formdata.map_to_dict(data, skip_none=False)
    expected_false = {
        "required": "value",
        "optional": "",
        "#-items": "3",
        "items-1": "a",
        "items-2": "",
        "items-3": "c",
    }
    assert actual_false == expected_false

    actual_true = formdata.map_to_dict(data, skip_none=True)
    expected_true = {
        "required": "value",
        "#-items": "2",
        "items-1": "a",
        "items-2": "c",
    }
    assert actual_true == expected_true


def test__map_to_dict_with_prefix__adds_prefix_to_all_keys() -> None:
    data = MixedModel(required="some-value", optional=None, items=["a", None, "c"])

    actual = formdata.map_to_dict(data, prefix="the-prefix", skip_none=True)

    expected = {
        "the-prefix-required": "some-value",
        "the-prefix-#-items": "2",
        "the-prefix-items-1": "a",
        "the-prefix-items-2": "c",
    }

    assert actual == expected
