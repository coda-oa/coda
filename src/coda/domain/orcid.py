from typing import Self, cast


class Orcid(str):
    def __new__(cls, orcid: str | None) -> Self:
        """
        Returns the ORCID identifier if it is valid, otherwise raises a ValueError.
        """
        instance = super().__new__(cls, orcid or "")
        if not instance:
            raise ValueError("ORCID is required")

        instance = cast(Self, instance.strip())
        instance = cast(Self, strip_url_components(instance))

        split = instance.split("-")
        if len(split) != 4 or not all(len(block) == 4 for block in split):
            raise ValueError("ORCID must consist of four blocks separated by hyphens")

        if instance[-1] != checksum(instance):
            raise ValueError("ORCID has an invalid checksum")

        return instance


def strip_url_components(orcid: str) -> str:
    return (
        orcid.removeprefix("https://")
        .removeprefix("http://")
        .removeprefix("www.")
        .removeprefix("sandbox.")
        .removeprefix("orcid.org/")
        .removesuffix("/")
    )


def checksum(orcid: str) -> str:
    """
    Calculate the checksum for an ORCID identifier.
    For more details see:
    https://support.orcid.org/hc/en-us/articles/360006897674-Structure-of-the-ORCID-Identifier
    """
    orcid = orcid.replace("-", "")
    total = 0
    for digit in orcid[:15]:
        total = (total + int(digit)) * 2
    remainder = total % 11
    result = (12 - remainder) % 11
    return "X" if result == 10 else str(result)
