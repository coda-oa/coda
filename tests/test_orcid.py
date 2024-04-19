import string
import unicodedata
import pytest

from coda import orcid


# NOTE: ORCIDs taken from https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier
JOSIAH_CARBERRY = "0000-0002-1825-0097"
LAUREL_HAAK = "0000-0001-5109-3700"
THOMAS_HICKEY = "0000-0002-1694-233X"
VALID_ORCIDS = [JOSIAH_CARBERRY, LAUREL_HAAK, THOMAS_HICKEY]


@pytest.mark.parametrize("valid_orcid", VALID_ORCIDS)
def test__a_valid_orcid__is_returned_unchanged(valid_orcid: str) -> None:
    assert orcid.Orcid(valid_orcid) == valid_orcid


@pytest.mark.parametrize("valid_orcid", VALID_ORCIDS)
def test__orcid_checksum__matches_last_char(valid_orcid: str) -> None:
    assert orcid.checksum(valid_orcid) == valid_orcid[-1]


def test__none_is_not_a_valid_orcid() -> None:
    with pytest.raises(ValueError):
        orcid.Orcid(None)


@pytest.mark.parametrize(
    "invalid_orcid",
    [
        "0000",
        "0000-0002",
        "0000-0002-1825",
        "000-002-825-097",
        JOSIAH_CARBERRY + "-0000",
        JOSIAH_CARBERRY.replace("-", ""),
    ],
)
def test__orcids_without_four_blocks_of_four_digits__are_invalid(invalid_orcid: str) -> None:
    with pytest.raises(ValueError):
        orcid.Orcid(invalid_orcid)


@pytest.mark.parametrize(
    "invalid_digit",
    [
        *(string.ascii_letters.replace("X", "")),
        *string.punctuation,
        unicodedata.lookup("SNOWMAN"),
    ],
)
def test__an_orcids_last_position_must_be_a_digit_or_X(invalid_digit: str) -> None:
    last = JOSIAH_CARBERRY[-1]
    with pytest.raises(ValueError):
        orcid.Orcid(JOSIAH_CARBERRY.replace(last, invalid_digit))


def test__orcids_with_an_invalid_checksum__are_invalid() -> None:
    with pytest.raises(ValueError):
        orcid.Orcid(JOSIAH_CARBERRY.replace(JOSIAH_CARBERRY[-1], "0"))


def test__orcids_with_leading_or_trailing_whitespace__get_trimmed() -> None:
    assert orcid.Orcid(f" {JOSIAH_CARBERRY} ") == JOSIAH_CARBERRY


@pytest.mark.parametrize(
    "orcid_address",
    [
        f"https://orcid.org/{JOSIAH_CARBERRY}/",
        f"http://orcid.org/{JOSIAH_CARBERRY}/",
        f"orcid.org/{JOSIAH_CARBERRY}",
        f"https://sandbox.orcid.org/{JOSIAH_CARBERRY}/",
        f"http://sandbox.orcid.org/{JOSIAH_CARBERRY}/",
        f"sandbox.orcid.org/{JOSIAH_CARBERRY}",
        f"https://www.orcid.org/{JOSIAH_CARBERRY}/",
        f"http://www.orcid.org/{JOSIAH_CARBERRY}/",
        f"www.orcid.org/{JOSIAH_CARBERRY}",
    ],
)
def test__orcids_with_orcid_address__get_stripped(orcid_address: str) -> None:
    assert orcid.Orcid(orcid_address) == JOSIAH_CARBERRY
