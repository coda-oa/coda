import math
from typing import cast

HUE_TOLERANCE = 1
TOLERANCE = 0.01


class Color:
    @staticmethod
    def from_rgb(red: int, green: int, blue: int) -> "Color":
        return Color(_rgb_to_hsl(red, green, blue))

    @staticmethod
    def from_hex(hex: str) -> "Color":
        r, g, b = int(hex[1:3], 16), int(hex[3:5], 16), int(hex[5:7], 16)
        return Color.from_rgb(r, g, b)

    @staticmethod
    def from_hsl(hue: float, saturation: float, lightness: float) -> "Color":
        return Color((hue, saturation, lightness))

    def __init__(self, hsl: tuple[float, float, float] = (0.0, 0.0, 0.0)) -> None:
        self._hsl = hsl

    def rgb(self) -> tuple[int, int, int]:
        return cast(
            tuple[int, int, int],
            tuple(int(round(c * 255)) for c in _hsl_to_rgb_normalized(*self._hsl)),
        )

    def hsl(self) -> tuple[float, float, float]:
        return self._hsl

    def hex(self) -> str:
        return "#" + "".join(map(_rgb_to_hex, self.rgb()))

    def __eq__(self, __value: object) -> bool:
        if not isinstance(__value, Color):
            raise TypeError("Cannot compare Color to non-Color")

        hue, saturation, lightness = self._hsl
        other_hue, other_saturation, other_lightness = __value._hsl
        hue_close = math.isclose(hue, other_hue, abs_tol=HUE_TOLERANCE)
        saturation_close = math.isclose(saturation, other_saturation, abs_tol=TOLERANCE)
        lightness_close = math.isclose(lightness, other_lightness, abs_tol=TOLERANCE)
        return hue_close and saturation_close and lightness_close


def _rgb_to_hex(val: int) -> str:
    return hex(val)[2:].zfill(2)


def _hsl_to_rgb_normalized(
    hue: float, saturation: float, lightness: float
) -> tuple[float, float, float]:
    C = (1 - abs(2 * lightness - 1)) * saturation
    h = hue / 60
    X = C * (1 - abs(h % 2 - 1))

    if h < 1:
        R, G, B = C, X, 0.0
    elif h < 2:
        R, G, B = X, C, 0.0
    elif h < 3:
        R, G, B = 0.0, C, X
    elif h < 4:
        R, G, B = 0.0, X, C
    elif h < 5:
        R, G, B = X, 0.0, C
    else:
        R, G, B = C, 0.0, X

    m = lightness - C / 2

    return R + m, G + m, B + m


def _rgb_to_hsl(red: int, green: int, blue: int) -> tuple[float, float, float]:
    R, G, B = red / 255, green / 255, blue / 255

    Xmax = max(R, G, B)
    Xmin = min(R, G, B)

    C = Xmax - Xmin

    L = (Xmax + Xmin) / 2

    if C == 0:
        H = 0.0
    elif Xmax == R:
        H = 60 * ((G - B) / C % 6)
    elif Xmax == G:
        H = 60 * ((B - R) / C + 2)
    else:
        H = 60 * ((R - G) / C + 4)

    if L == 0 or L == 1:
        S = 0.0
    else:
        S = C / (1 - abs(2 * L - 1))

    return H, S, L
