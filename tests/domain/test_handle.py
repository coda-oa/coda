import pytest

from coda.domain.publication.links import Handle


def test_can_create_handle() -> None:
    sut = Handle("1234/5678")

    assert str(sut) == "1234/5678"
    assert sut.value() == "1234/5678"


def test_handle_with_leading_or_trailing_whitespace_gets_trimmed() -> None:
    sut = Handle(" 10.1234/5678 ")

    assert str(sut) == "10.1234/5678"


@pytest.mark.parametrize(
    "valid_handle",
    [
        "1234/5678",
        "10.1234/5678",
        "20.500.12345/67890",
        "hdl:1234/5678",
        "hdl:10.1234/5678",
        "https://hdl.handle.net/1234/5678",
        "https://hdl.handle.net/10.1234/5678",
        "http://hdl.handle.net/1234/5678",
    ],
)
def test_valid_handle_formats(valid_handle: str) -> None:
    sut = Handle(valid_handle)
    # Should normalize to simple prefix/suffix format
    assert "/" in str(sut)
    assert not str(sut).startswith("hdl:")
    assert not str(sut).startswith("http")


@pytest.mark.parametrize(
    "invalid_handle",
    [
        "",
        " ",
        "1234",  # no slash
        "/5678",  # no prefix
        "1234/",  # no suffix
        "1234//5678",  # double slash
    ],
)
def test_invalid_handle_formats(invalid_handle: str) -> None:
    with pytest.raises(ValueError):
        Handle(invalid_handle)


def test_handle_url_returns_handle_net_url() -> None:
    sut = Handle("1234/5678")

    assert sut.url() == "https://hdl.handle.net/1234/5678"


def test_handle_removes_hdl_prefix() -> None:
    sut = Handle("hdl:1234/5678")

    assert str(sut) == "1234/5678"


def test_handle_removes_url_prefix() -> None:
    sut = Handle("https://hdl.handle.net/1234/5678")

    assert str(sut) == "1234/5678"
