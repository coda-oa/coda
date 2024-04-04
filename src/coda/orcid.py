def parse(orcid: str | None) -> str:
    """
    Returns the ORCID identifier if it is valid, otherwise raises a ValueError.
    """
    if not orcid:
        raise ValueError("ORCID is required")

    orcid = orcid.strip()
    orcid = strip_url_components(orcid)

    split = orcid.split("-")
    if len(split) != 4 or not all(len(block) == 4 for block in split):
        raise ValueError("ORCID must consist of four blocks separated by hyphens")

    if orcid[-1] != checksum(orcid):
        raise ValueError("ORCID has an invalid checksum")

    return orcid


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
