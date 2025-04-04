class Issn(str):
    def __new__(cls, value: str) -> "Issn":
        value = value.strip()
        if len(value) != 9:
            raise ValueError(f"ISSN must have length 9, got {len(value)}")

        if checksum(value) != value[-1]:
            raise ValueError(f"ISSN has invalid checksum: {value}")

        return super().__new__(cls, value)


def checksum(issn: str) -> str:
    """
    Calculate the checksum for an ISSN.
    For more details see:
    https://en.wikipedia.org/wiki/International_Standard_Serial_Number
    """
    issn = issn.replace("-", "")
    total = 0
    for i, digit in enumerate(issn[:7]):
        total += int(digit) * (8 - i)
    remainder = total % 11
    result = 0 if remainder == 0 else 11 - remainder
    return "X" if result == 10 else str(result)
