import pytest

from coda.color import HUE_TOLERANCE, TOLERANCE, Color


def assert_close_hsl(a: tuple[float, float, float], b: tuple[float, float, float]) -> None:
    assert a[0] == pytest.approx(b[0], abs=HUE_TOLERANCE)
    assert a[1] == pytest.approx(b[1], abs=TOLERANCE)
    assert a[2] == pytest.approx(b[2], abs=TOLERANCE)


def test__default_color_is_black() -> None:
    sut = Color()
    assert sut.rgb() == (0, 0, 0)
    assert sut.hex() == "#000000"


def test__color_from_rgb__returns_same_rgb() -> None:
    sut = Color.from_rgb(234, 123, 0)

    assert sut.rgb() == (234, 123, 0)


def test__color_from_rgb__can_convert_to_other_formats() -> None:
    sut = Color.from_rgb(234, 12, 8)

    assert sut.hex() == "#ea0c08"
    assert_close_hsl(sut.hsl(), (1, 0.93, 0.47))


def test__color_from_hex__returns_same_hex() -> None:
    sut = Color.from_hex("#ea0c08")

    assert sut.hex() == "#ea0c08"


def test__color_from_hex__can_convert_to_rgb() -> None:
    sut = Color.from_hex("#ea0c08")

    assert sut.rgb() == (234, 12, 8)


def test__color_from_hsl__returns_same_hsl() -> None:
    sut = Color.from_hsl(203, 0.47, 0.17)

    assert sut.hsl() == pytest.approx((203, 0.47, 0.17), abs=TOLERANCE)


def test__color_from_hsl__can_convert_to_other_formats() -> None:
    sut = Color.from_hsl(203, 0.47, 0.17)

    assert sut.rgb() == (23, 48, 64)
    assert sut.hex() == "#173040"


def test__different_instances_of_same_color_are_equal() -> None:
    first = Color.from_hex("#ea0c08")
    second = Color.from_rgb(234, 12, 8)
    third = Color.from_hsl(1, 0.93, 0.47)

    assert first == second
    assert first == third
    assert second == third


def test__two_instances_of_different_color_are_not_equal() -> None:
    first = Color.from_hex("#ea0c08")
    second = Color.from_rgb(204, 50, 102)

    assert first != second


def test__color_cannot_be_compared_to_non_color() -> None:
    with pytest.raises(TypeError):
        Color() == 1

    with pytest.raises(TypeError):
        Color() == "string"
