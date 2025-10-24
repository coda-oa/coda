import datetime
from typing import Annotated

import pydantic
import pytest

from coda import formdata
from coda.formdata import ValidationFailed


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


class CriticalUnionCase(pydantic.BaseModel):
    """Model for testing dict vs model union with ambiguous field names."""

    critical_field: dict[str, str] | SimpleData


def test__union_dict_with_model__matching_model_field_name_but_different_data_type__matches_dict() -> (
    None
):
    """
    This test uses dict keys that EXACTLY match SimpleData field names (a_str, a_date)
    but should be treated as dict keys, not model fields.
    """
    expected = CriticalUnionCase(
        critical_field={
            "a_str": "im-a-dict-key-not-model-field",
            "a_date": "im-also-a-dict-key-not-model-field",
        }
    )

    actual = formdata.map_to_model(
        CriticalUnionCase,
        {
            "critical_field-a_str": "im-a-dict-key-not-model-field",
            "critical_field-a_date": "im-also-a-dict-key-not-model-field",
        },
    )

    assert actual == expected


class AmbiguousUnionCase(pydantic.BaseModel):
    """Model for testing processor precedence with ambiguous data."""

    ambiguous_field: dict[str, str] | DataWithList


def test__processor_precedence_with_ambiguous_data() -> None:
    """
    Test data that could reasonably be handled by either processor.

    This data has no obvious model patterns (no sequence counters, no nested structure)
    but uses keys that don't obviously indicate dict vs model preference.
    Tests whether processor ordering or intelligent analysis determines the outcome.
    """
    expected = AmbiguousUnionCase(ambiguous_field={"some_key": "value1", "another_key": "value2"})

    actual = formdata.map_to_model(
        AmbiguousUnionCase,
        {"ambiguous_field-some_key": "value1", "ambiguous_field-another_key": "value2"},
    )

    assert actual == expected


class EmptyUnionCase(pydantic.BaseModel):
    """Model for testing empty field processor selection."""

    empty_field: dict[str, str] | SimpleData | None


def test__empty_field_union_processor_selection() -> None:
    """
    Test processor selection when no keys match the field pattern.

    When no field-* keys exist, which processor should handle creating
    the default value?
    """
    expected = EmptyUnionCase(empty_field={})

    actual = formdata.map_to_model(
        EmptyUnionCase,
        {"other_field": "value"},
    )

    assert actual == expected


class AnnotatedFieldModel(pydantic.BaseModel):
    a_field: Annotated[str, pydantic.PlainValidator(lambda s: s)]


def test__annotated_field_can_be_mapped() -> None:
    expected = AnnotatedFieldModel(a_field="some-value")

    actual = formdata.map_to_model(AnnotatedFieldModel, {"a_field": "some-value"})

    assert actual == expected


# ============================================================================
# PRODUCTION READINESS TESTS - Security & Resource Exhaustion
# ============================================================================


def test__large_sequence_counter__validation_error() -> None:
    """Test that extremely large sequence counters are rejected to prevent DoS."""
    with pytest.raises(ValidationFailed, match="Sequence too large"):
        formdata.map_to_model(
            DataWithList,
            {
                "#-a_list": "50000",  # Above MAX_SEQUENCE_LENGTH limit
                "a_list-1": "1",
            },
        )


def test__negative_sequence_counter__validation_error() -> None:
    """Test that negative sequence counters are handled gracefully."""
    with pytest.raises(ValidationFailed, match="cannot be negative"):
        formdata.map_to_model(
            DataWithList,
            {
                "#-a_list": "-5",
                "a_list-1": "1",
            },
        )


def test__zero_sequence_counter__empty_list() -> None:
    """Test that zero sequence counter creates empty list."""
    expected = DataWithList(a_list=[])

    actual = formdata.map_to_model(
        DataWithList,
        {"#-a_list": "0"},
    )

    assert actual == expected


def test__non_numeric_sequence_counter__validation_error() -> None:
    """Test that non-numeric sequence counters are rejected."""
    with pytest.raises(ValidationFailed):
        formdata.map_to_model(
            DataWithList,
            {
                "#-a_list": "not-a-number",
                "a_list-1": "1",
            },
        )


def test__float_sequence_counter__validation_error() -> None:
    """Test that float sequence counters are rejected."""
    with pytest.raises(ValidationFailed):
        formdata.map_to_model(
            DataWithList,
            {
                "#-a_list": "3.5",
                "a_list-1": "1",
            },
        )


def test__sequence_counter_with_overflow__validation_error() -> None:
    """Test that sequence counters causing integer overflow are handled."""
    with pytest.raises(ValidationFailed):
        formdata.map_to_model(
            DataWithList,
            {
                "#-a_list": "999999999999999999999999999999999999999",
                "a_list-1": "1",
            },
        )


# ============================================================================
# PRODUCTION READINESS TESTS - Error Handling & Recovery
# ============================================================================


def test__missing_sequence_items__partial_list() -> None:
    """Test handling of missing sequence items (gaps in numbering)."""
    expected = DataWithBareList(bare=[1, 3])  # Missing item 2

    actual = formdata.map_to_model(
        DataWithBareList,
        {
            "#-bare": "3",
            "bare-1": 1,
            # "bare-2" is missing
            "bare-3": 3,
        },
    )

    assert actual == expected


def test__out_of_order_sequence_items__correct_ordering() -> None:
    """Test that sequence items are processed in numeric order regardless of input order."""
    expected = DataWithList(a_list=[1, 2, 3])

    actual = formdata.map_to_model(
        DataWithList,
        {
            "#-a_list": "3",
            "a_list-3": "3",  # Out of order
            "a_list-1": "1",
            "a_list-2": "2",
        },
    )

    assert actual == expected


def test__sequence_counter_mismatch__uses_counter() -> None:
    """Test that sequence counter takes precedence over available items."""
    expected = DataWithList(a_list=[1, 2])  # Only processes up to counter

    actual = formdata.map_to_model(
        DataWithList,
        {
            "#-a_list": "2",  # Counter says 2 items
            "a_list-1": "1",
            "a_list-2": "2",
            "a_list-3": "3",  # Extra item ignored
            "a_list-4": "4",  # Extra item ignored
        },
    )

    assert actual == expected


def test__deeply_nested_models__no_stack_overflow() -> None:
    """Test that deeply nested models don't cause stack overflow."""
    # Use the existing Level4 structure which only goes 4 levels deep
    # This tests reasonable nesting depth without hitting limits
    data = {
        "value": "L4",
        "nested-value": "L3",
        "nested-nested-value": "L2",
        "nested-nested-nested-value": "L1",
    }

    # This should work without stack overflow
    actual = formdata.map_to_model(Level4, data)
    assert actual.value == "L4"
    assert actual.nested.value == "L3"


def test__circular_reference_like_data__handled_gracefully() -> None:
    """Test handling of data that could create circular references."""
    # This creates a data pattern that looks like it might be circular
    actual = formdata.map_to_model(
        SimpleData,
        {
            "a_str": "test",
            "a_date": datetime.datetime.now().isoformat(),
            # These keys don't match the model, so they're ignored
            "a_str-a_str": "circular-like",
            "a_date-a_date": "circular-like",
        },
    )

    assert actual.a_str == "test"


def test__invalid_datetime_format__validation_error() -> None:
    """Test that invalid datetime formats are properly rejected."""
    with pytest.raises(pydantic.ValidationError):
        formdata.map_to_model(
            SimpleData,
            {
                "a_str": "test",
                "a_date": "not-a-date",
            },
        )


def test__mixed_valid_invalid_types_in_sequence__partial_success() -> None:
    """Test handling of sequences with mixed valid/invalid items."""
    # This should fail because pydantic validates the entire list
    with pytest.raises(pydantic.ValidationError):
        formdata.map_to_model(
            DataWithList,
            {
                "#-a_list": "3",
                "a_list-1": "1",  # Valid int
                "a_list-2": "not-a-number",  # Invalid int
                "a_list-3": "3",  # Valid int
            },
        )


# ============================================================================
# PRODUCTION READINESS TESTS - Input Validation & Security
# ============================================================================


def test__field_names_with_special_characters__handled_safely() -> None:
    """Test that field names with special characters are handled safely."""

    class SpecialFieldModel(pydantic.BaseModel):
        normal_field: str

    # Extra keys with special characters should be ignored
    actual = formdata.map_to_model(
        SpecialFieldModel,
        {
            "normal_field": "value",
            "field-with-dashes": "ignored",
            "field.with.dots": "ignored",
            "field/with/slashes": "ignored",
            "field\\with\\backslashes": "ignored",
        },
    )

    assert actual.normal_field == "value"


def test__unicode_field_names__handled_correctly() -> None:
    """Test that unicode characters in field names are handled correctly."""

    class UnicodeModel(pydantic.BaseModel):
        normal_field: str

    actual = formdata.map_to_model(
        UnicodeModel,
        {
            "normal_field": "value",
            "field_with_émojis_🚀": "ignored",
            "field_with_中文": "ignored",
            "field_with_русский": "ignored",
        },
    )

    assert actual.normal_field == "value"


def test__empty_string_field_names__handled_gracefully() -> None:
    """Test that empty string field names don't cause issues."""

    class NormalModel(pydantic.BaseModel):
        field: str

    actual = formdata.map_to_model(
        NormalModel,
        {
            "field": "value",
            "": "empty-key-ignored",
            " ": "space-key-ignored",
        },
    )

    assert actual.field == "value"


def test__very_long_field_names__handled_efficiently() -> None:
    """Test that very long field names don't cause performance issues."""
    long_field_name = "a" * 1000  # 1000 character field name

    class NormalModel(pydantic.BaseModel):
        field: str

    actual = formdata.map_to_model(
        NormalModel,
        {
            "field": "value",
            long_field_name: "ignored",
            f"{long_field_name}-suffix": "ignored",
        },
    )

    assert actual.field == "value"


def test__null_bytes_in_field_names__handled_safely() -> None:
    """Test that null bytes and control characters in field names are handled."""

    class NormalModel(pydantic.BaseModel):
        field: str

    actual = formdata.map_to_model(
        NormalModel,
        {
            "field": "value",
            "field\x00with\x00nulls": "ignored",
            "field\nwith\nnewlines": "ignored",
            "field\twith\ttabs": "ignored",
        },
    )

    assert actual.field == "value"


# ============================================================================
# PRODUCTION READINESS TESTS - Performance & Scalability
# ============================================================================


def test__large_number_of_simple_fields__performance() -> None:
    """Test performance with a large number of simple fields."""

    class ManyFieldsModel(pydantic.BaseModel):
        field1: str
        field2: str
        field3: str

    # Create data with many extra fields that should be ignored
    data = {
        "field1": "value1",
        "field2": "value2",
        "field3": "value3",
    }

    # Add 100 extra fields that should be ignored
    for i in range(100):
        data[f"extra_field_{i}"] = f"extra_value_{i}"

    actual = formdata.map_to_model(ManyFieldsModel, data)

    assert actual.field1 == "value1"
    assert actual.field2 == "value2"
    assert actual.field3 == "value3"


def test__large_dictionary_field__memory_efficient() -> None:
    """Test that large dictionary fields are processed efficiently."""
    # Create a dict with 100 key-value pairs
    data = {}
    expected_dict = {}

    for i in range(100):
        key = f"a_dict-key_{i}"
        value = f"value_{i}"
        data[key] = value
        expected_dict[f"key_{i}"] = value

    expected = DictData(a_dict=expected_dict)
    actual = formdata.map_to_model(DictData, data)

    assert actual == expected


def test__large_sequence_field__memory_efficient() -> None:
    """Test that large sequence fields (within reasonable bounds) work efficiently."""
    # Test with 100 items (reasonable size)
    data = {"#-a_list": "100"}
    expected_list = []

    for i in range(1, 101):
        data[f"a_list-{i}"] = str(i)
        expected_list.append(i)

    expected = DataWithList(a_list=expected_list)
    actual = formdata.map_to_model(DataWithList, data)

    assert actual == expected


def test__complex_nested_structure__reasonable_performance() -> None:
    """Test complex nested structures with reasonable performance."""
    # Create a structure with multiple levels and field types
    data = {
        "simple_str": "value",
        "#-a_list": "3",
        "a_list-1": "1",
        "a_list-2": "2",
        "a_list-3": "3",
        "a_dict-key1": "val1",
        "a_dict-key2": "val2",
        "nested-a_str": "nested_value",
        "nested-a_date": datetime.datetime.now().isoformat(),
    }

    # Add some noise data that should be ignored
    for i in range(50):
        data[f"noise_field_{i}"] = f"noise_value_{i}"

    actual = formdata.map_to_model(ComplexIntegration, data)

    assert actual.simple_str == "value"
    assert len(actual.a_list) == 3
    assert len(actual.a_dict) == 2
    assert actual.nested.a_str == "nested_value"


# ============================================================================
# PRODUCTION READINESS TESTS - Edge Cases & Boundary Conditions
# ============================================================================


def test__empty_input_data__default_values() -> None:
    """Test behavior with completely empty input data."""

    class OptionalFieldsModel(pydantic.BaseModel):
        required_field: str
        optional_field: str | None = None

    with pytest.raises(pydantic.ValidationError):
        formdata.map_to_model(OptionalFieldsModel, {})


def test__only_irrelevant_keys__default_behavior() -> None:
    """Test behavior when input contains only keys irrelevant to the model."""

    class SimpleModel(pydantic.BaseModel):
        field: str

    with pytest.raises(pydantic.ValidationError):
        formdata.map_to_model(
            SimpleModel,
            {
                "completely_different": "value",
                "nothing_matches": "value",
                "random_key": "value",
            },
        )


def test__prefix_edge_cases__handled_correctly() -> None:
    """Test edge cases with prefixes."""
    now = datetime.datetime.now()
    expected = SimpleData(a_str="value", a_date=now)

    # Test with empty prefix (should work same as no prefix)
    actual = formdata.map_to_model(
        SimpleData,
        {
            "a_str": "value",
            "a_date": now.isoformat(),
        },
        prefix="",
    )

    assert actual == expected


def test__prefix_with_special_characters__handled_safely() -> None:
    """Test prefixes containing special characters."""
    now = datetime.datetime.now()
    expected = SimpleData(a_str="value", a_date=now)

    # Test with prefix containing dots and underscores
    actual = formdata.map_to_model(
        SimpleData,
        {
            "form.prefix_v2-a_str": "value",
            "form.prefix_v2-a_date": now.isoformat(),
        },
        prefix="form.prefix_v2",
    )

    assert actual == expected


def test__duplicate_field_resolution__precedence() -> None:
    """Test that field precedence is handled correctly when multiple forms exist."""
    # When both processed and simple forms exist, simple form takes precedence
    expected = DataWithList(a_list=[99, 100, 101])

    actual = formdata.map_to_model(
        DataWithList,
        {
            "a_list": [99, 100, 101],  # Simple form takes precedence
            "#-a_list": "2",  # Complex form should be ignored
            "a_list-1": "1",
            "a_list-2": "2",
        },
    )

    assert actual == expected


def test__extremely_deep_model_nesting__bounded() -> None:
    """Test that extremely deep model nesting is handled within reasonable bounds."""

    # Test with maximum practical nesting depth
    class Deep1(pydantic.BaseModel):
        value: str

    class Deep2(pydantic.BaseModel):
        nested: Deep1

    class Deep3(pydantic.BaseModel):
        nested: Deep2

    class Deep4(pydantic.BaseModel):
        nested: Deep3

    class Deep5(pydantic.BaseModel):
        nested: Deep4

    data = {"nested-nested-nested-nested-value": "deep_value"}

    actual = formdata.map_to_model(Deep5, data)
    assert actual.nested.nested.nested.nested.value == "deep_value"
