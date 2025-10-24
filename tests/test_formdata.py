import datetime

import pydantic
import pytest

from coda import formdata


class SimpleData(pydantic.BaseModel):
    a_str: str
    a_date: datetime.datetime


def test__simple_data__can_be_mapped_to_model() -> None:
    now = datetime.datetime.now()
    expected = SimpleData(a_str="the-value", a_date=now)

    actual = formdata.map_to_model(
        SimpleData,
        {
            "a_str": "the-value",
            "a_date": now.isoformat(),
        },
    )

    assert actual == expected


def test__prefixed_data__can_be_mapped_to_model() -> None:
    now = datetime.datetime.now()
    expected = SimpleData(a_str="the-value", a_date=now)

    actual = formdata.map_to_model(
        SimpleData,
        {
            "the-prefix-a_str": "the-value",
            "the-prefix-a_date": now.isoformat(),
        },
        prefix="the-prefix",
    )

    assert actual == expected


class DataWithList(pydantic.BaseModel):
    a_list: list[int]


class DataWithTuple(pydantic.BaseModel):
    a_list: tuple[int, ...]


class DataWithOptionalList(pydantic.BaseModel):
    opt_list: list[str] | None = None


class DataWithBareList(pydantic.BaseModel):
    bare: list  # type: ignore


@pytest.mark.parametrize("model", (DataWithList, DataWithTuple))
def test__data_with_list__list_in_dict__maps_to_data(
    model: type[DataWithList] | type[DataWithTuple],
) -> None:
    expected = model(a_list=[1, 2, 3])

    actual = formdata.map_to_model(model, {"a_list": ["1", "2", 3]})

    assert actual == expected


@pytest.mark.parametrize("model", (DataWithList, DataWithTuple))
def test__data_with_list__list_in_flat_form__maps_to_data(
    model: type[DataWithList] | type[DataWithTuple],
) -> None:
    expected = model(a_list=[1, 2, 3])

    actual = formdata.map_to_model(
        model,
        {
            "#-a_list": "3",
            "a_list-1": 1,
            "a_list-2": "2",
            "a_list-3": 3,
        },
    )

    assert actual == expected


def test__optional_list_field__is_detected() -> None:
    """Test that list[T] | None fields are properly detected."""
    expected = DataWithOptionalList(opt_list=["a", "b"])

    actual = formdata.map_to_model(
        DataWithOptionalList,
        {
            "#-opt_list": "2",
            "opt_list-1": "a",
            "opt_list-2": "b",
        },
    )

    assert actual == expected


def test__bare_list_field__is_detected() -> None:
    expected = DataWithBareList(bare=[1, 2, 3])

    actual = formdata.map_to_model(
        DataWithBareList,
        {
            "#-bare": "3",
            "bare-1": 1,
            "bare-2": 2,
            "bare-3": 3,
        },
    )

    assert actual == expected


class StrOrList(pydantic.BaseModel):
    str_or_list: str | list[str]


def test__str_or_list_annotation__data_with_str__maps_to_model() -> None:
    expected = StrOrList(str_or_list="a-value")

    actual = formdata.map_to_model(StrOrList, {"str_or_list": "a-value"})

    assert expected == actual


def test__str_or_list_annotation__data_with_list__maps_to_model() -> None:
    expected = StrOrList(str_or_list=["1", "2", "3"])

    actual = formdata.map_to_model(
        StrOrList,
        {
            "#-str_or_list": "3",
            "str_or_list-1": "1",
            "str_or_list-2": "2",
            "str_or_list-3": "3",
        },
    )

    assert expected == actual


class DictData(pydantic.BaseModel):
    a_dict: dict[str, str]


def test__dict_model__data_with_dict_keys__maps_to_model() -> None:
    expected = DictData(a_dict={"first": "1", "second": "2"})

    actual = formdata.map_to_model(
        DictData,
        {
            "a_dict-first": "1",
            "a_dict-second": "2",
        },
    )

    assert actual == expected


class StrOrDict(pydantic.BaseModel):
    a_dict: dict[str, str] | str


def test__str_or_dict__data_with_str__maps_to_model() -> None:
    expected = StrOrDict(a_dict="a-value")

    actual = formdata.map_to_model(
        StrOrDict,
        {"a_dict": "a-value"},
    )

    assert actual == expected


def test__str_or_dict__data_with_dict__maps_to_model() -> None:
    expected = StrOrDict(a_dict={"first": "1", "second": "2"})

    actual = formdata.map_to_model(
        StrOrDict,
        {
            "a_dict-first": "1",
            "a_dict-second": "2",
        },
    )

    assert actual == expected


class ValueListAndDict(pydantic.BaseModel):
    a_value: bool
    a_list: list[str]
    a_dict: dict[int, str]


def test__a_value_a_list_and_dict__maps_to_model() -> None:
    expected = ValueListAndDict(
        a_value=True,
        a_list=["a", "b"],
        a_dict={1: "x", 2: "y"},
    )

    actual = formdata.map_to_model(
        ValueListAndDict,
        {
            "a_value": "true",
            "#-a_list": 2,
            "a_list-1": "a",
            "a_list-2": "b",
            "a_dict-1": "x",
            "a_dict-2": "y",
        },
    )

    assert actual == expected


class ParentData(pydantic.BaseModel):
    a_value: str
    nested: ValueListAndDict


def test__can_map_nested_model() -> None:
    expected = ParentData(
        a_value="some-value",
        nested=ValueListAndDict(
            a_value=True,
            a_list=["a", "b"],
            a_dict={1: "x", 2: "y"},
        ),
    )

    actual = formdata.map_to_model(
        ParentData,
        {
            "a_value": "some-value",
            "nested-a_value": "true",
            "nested-#-a_list": 2,
            "nested-a_list-1": "a",
            "nested-a_list-2": "b",
            "nested-a_dict-1": "x",
            "nested-a_dict-2": "y",
        },
    )

    assert actual == expected


class ModelOrDict(pydantic.BaseModel):
    model_or_dict: dict[str, int] | ValueListAndDict


def test__model_or_dict__data_with_dict__maps_to_model() -> None:
    expected = ModelOrDict(
        model_or_dict={
            "a-key": 10,
            "b-key": 42,
        }
    )

    actual = formdata.map_to_model(
        ModelOrDict,
        {
            "model_or_dict-a-key": 10,
            "model_or_dict-b-key": 42,
        },
    )

    assert actual == expected


def test__model_or_dict__data_with_model__maps_to_model() -> None:
    expected = ModelOrDict(
        model_or_dict=ValueListAndDict(
            a_value=False,
            a_list=["a", "b"],
            a_dict={1: "x", 2: "y"},
        )
    )

    actual = formdata.map_to_model(
        ModelOrDict,
        {
            "model_or_dict-a_value": "false",
            "model_or_dict-#-a_list": "2",
            "model_or_dict-a_list-1": "a",
            "model_or_dict-a_list-2": "b",
            "model_or_dict-a_dict-1": "x",
            "model_or_dict-a_dict-2": "y",
        },
    )

    assert actual == expected


class ModelUnion(pydantic.BaseModel):
    which_one: SimpleData | DataWithList


def test__model_union__can_map_data_with_simple_model() -> None:
    now = datetime.datetime.now()
    expected = ModelUnion(which_one=SimpleData(a_str="some-value", a_date=now))

    actual = formdata.map_to_model(
        ModelUnion,
        {
            "which_one-a_str": "some-value",
            "which_one-a_date": now.isoformat(),
        },
    )

    assert actual == expected


def test__model_union__can_map_data_with_list_model() -> None:
    expected = ModelUnion(which_one=DataWithList(a_list=[1, 2]))

    actual = formdata.map_to_model(
        ModelUnion,
        {
            "which_one-#-a_list": "2",
            "which_one-a_list-1": "1",
            "which_one-a_list-2": "2",
        },
    )

    assert actual == expected


class OptionalModel(pydantic.BaseModel):
    a_value: str
    nested: SimpleData | None = None


def test__optional_model_field__with_no_nested_data() -> None:
    expected = OptionalModel(a_value="test", nested=None)

    actual = formdata.map_to_model(
        OptionalModel,
        {"a_value": "test"},
    )

    assert actual == expected


def test__optional_model_field__with_nested_data() -> None:
    now = datetime.datetime.now()
    expected = OptionalModel(
        a_value="test",
        nested=SimpleData(a_str="nested-value", a_date=now),
    )

    actual = formdata.map_to_model(
        OptionalModel,
        {
            "a_value": "test",
            "nested-a_str": "nested-value",
            "nested-a_date": now.isoformat(),
        },
    )

    assert actual == expected


def test__field_already_present_in_data__skips_processing() -> None:
    data_dict = {
        "a_list": [99, 100],
        "#-a_list": "2",
        "a_list-1": "1",
        "a_list-2": "2",
    }

    actual = formdata.map_to_model(DataWithList, data_dict)

    assert actual.a_list == [99, 100]


def test__nested_field_already_present__skips_nested_processing() -> None:
    nested_instance = ValueListAndDict(
        a_value=False,
        a_list=["x", "y"],
        a_dict={99: "z"},
    )

    actual = formdata.map_to_model(
        ParentData,
        {
            "a_value": "parent-value",
            "nested": nested_instance,
            "nested-a_value": "ignored",
        },
    )

    assert actual.a_value == "parent-value"
    assert actual.nested == nested_instance


def test__dict_field_already_present__skips_dict_processing() -> None:
    actual = formdata.map_to_model(
        DictData,
        {
            "a_dict": {"prebuilt": "value"},
            "a_dict-ignored": "should-not-appear",
        },
    )

    assert actual.a_dict == {"prebuilt": "value"}


class ComplexIntegration(pydantic.BaseModel):
    simple_str: str
    a_list: list[int]
    a_dict: dict[str, str]
    nested: SimpleData


def test__multiple_field_types_together__integration() -> None:
    now = datetime.datetime.now()
    expected = ComplexIntegration(
        simple_str="value",
        a_list=[1, 2, 3],
        a_dict={"key1": "val1", "key2": "val2"},
        nested=SimpleData(a_str="nested", a_date=now),
    )

    actual = formdata.map_to_model(
        ComplexIntegration,
        {
            "simple_str": "value",
            "#-a_list": "3",
            "a_list-1": "1",
            "a_list-2": "2",
            "a_list-3": "3",
            "a_dict-key1": "val1",
            "a_dict-key2": "val2",
            "nested-a_str": "nested",
            "nested-a_date": now.isoformat(),
        },
    )

    assert actual == expected


class Level1(pydantic.BaseModel):
    value: str


class Level2(pydantic.BaseModel):
    value: str
    nested: Level1


class Level3(pydantic.BaseModel):
    value: str
    nested: Level2


class Level4(pydantic.BaseModel):
    value: str
    nested: Level3


def test__deeply_nested_models__four_levels() -> None:
    expected = Level4(
        value="L4",
        nested=Level3(
            value="L3",
            nested=Level2(
                value="L2",
                nested=Level1(value="L1"),
            ),
        ),
    )

    actual = formdata.map_to_model(
        Level4,
        {
            "value": "L4",
            "nested-value": "L3",
            "nested-nested-value": "L2",
            "nested-nested-nested-value": "L1",
        },
    )

    assert actual == expected


class Model1(pydantic.BaseModel):
    field1: str


class Model2(pydantic.BaseModel):
    field2: int


class Model3(pydantic.BaseModel):
    field3: bool


class ThreeModelUnion(pydantic.BaseModel):
    which: Model1 | Model2 | Model3


def test__union_of_three_models__matches_first() -> None:
    expected = ThreeModelUnion(which=Model1(field1="test"))

    actual = formdata.map_to_model(
        ThreeModelUnion,
        {"which-field1": "test"},
    )

    assert actual == expected


def test__union_of_three_models__matches_second() -> None:
    expected = ThreeModelUnion(which=Model2(field2=42))

    actual = formdata.map_to_model(
        ThreeModelUnion,
        {"which-field2": "42"},
    )

    assert actual == expected


def test__union_of_three_models__matches_third() -> None:
    expected = ThreeModelUnion(which=Model3(field3=True))

    actual = formdata.map_to_model(
        ThreeModelUnion,
        {"which-field3": "true"},
    )

    assert actual == expected


class GrandParent(pydantic.BaseModel):
    a_value: str
    nested: ParentData


def test__prefixed_sequence_field__with_parent_prefix() -> None:
    expected = GrandParent(
        a_value="grand",
        nested=ParentData(
            a_value="parent",
            nested=ValueListAndDict(
                a_value=True,
                a_list=["x", "y", "z"],
                a_dict={1: "a"},
            ),
        ),
    )

    actual = formdata.map_to_model(
        GrandParent,
        {
            "gp-a_value": "grand",
            "gp-nested-a_value": "parent",
            "gp-nested-nested-a_value": "true",
            "gp-nested-nested-#-a_list": "3",
            "gp-nested-nested-a_list-1": "x",
            "gp-nested-nested-a_list-2": "y",
            "gp-nested-nested-a_list-3": "z",
            "gp-nested-nested-a_dict-1": "a",
        },
        prefix="gp",
    )

    assert actual == expected


def test__empty_dict_field__no_matching_keys() -> None:
    actual = formdata.map_to_model(
        DictData,
        {
            "other_key": "value",
            "another_key": "value",
        },
    )

    assert actual.a_dict == {}


def test__no_matching_model_in_union__uses_first_and_fails() -> None:
    with pytest.raises(pydantic.ValidationError):
        formdata.map_to_model(
            ModelUnion,
            {
                "which_one-unknown_field": "value",
                "which_one-another_unknown": "value",
            },
        )


def test__extra_keys_in_data__ignored_by_model() -> None:
    now = datetime.datetime.now()
    expected = SimpleData(a_str="value", a_date=now)

    actual = formdata.map_to_model(
        SimpleData,
        {
            "a_str": "value",
            "a_date": now.isoformat(),
            "extra_key": "ignored",
            "another_extra": 123,
        },
    )

    assert actual == expected


def test__counter_key_missing__field_required_error() -> None:
    with pytest.raises(pydantic.ValidationError):
        formdata.map_to_model(
            DataWithList,
            {
                "a_list-1": "1",
                "a_list-2": "2",
            },
        )


class IntKeyDict(pydantic.BaseModel):
    int_dict: dict[int, str]


def test__dict_with_int_keys() -> None:
    expected = IntKeyDict(int_dict={1: "one", 2: "two", 10: "ten"})

    actual = formdata.map_to_model(
        IntKeyDict,
        {
            "int_dict-1": "one",
            "int_dict-2": "two",
            "int_dict-10": "ten",
        },
    )

    assert actual == expected


class StrData(pydantic.BaseModel):
    a_str: str


class ListOfStrData(pydantic.BaseModel):
    str_data: list[StrData]


def test__list_of_nested_models_can_be_mapped() -> None:
    expected = ListOfStrData(
        str_data=[
            StrData(a_str="value-1"),
            StrData(a_str="value-2"),
        ]
    )

    actual = formdata.map_to_model(
        ListOfStrData,
        {
            "#-str_data": 2,
            "str_data-1-a_str": "value-1",
            "str_data-2-a_str": "value-2",
        },
    )

    assert actual == expected


class ListOfStrDataOrInt(pydantic.BaseModel):
    str_data: list[StrData | int]


def test__list_of_nested_union_list_can_be_mapped() -> None:
    expected = ListOfStrDataOrInt(
        str_data=[
            42,
            StrData(a_str="some-value"),
        ]
    )

    actual = formdata.map_to_model(
        ListOfStrDataOrInt,
        {
            "#-str_data": 2,
            "str_data-1": 42,
            "str_data-2-a_str": "some-value",
        },
    )

    assert actual == expected


class ListOfModelUnions(pydantic.BaseModel):
    data: list[StrData | DictData]


def test__list_of_model_unions_can_be_mapped() -> None:
    expected = ListOfModelUnions(
        data=[
            DictData(a_dict={"a": "some-value"}),
            StrData(a_str="another-value"),
        ]
    )

    actual = formdata.map_to_model(
        ListOfModelUnions,
        {
            "#-data": 2,
            "data-1-a_dict-a": "some-value",
            "data-2-a_str": "another-value",
        },
    )

    assert actual == expected
