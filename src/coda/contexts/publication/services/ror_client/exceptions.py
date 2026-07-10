from coda.domain.errors import DomainError


class RORClientError(DomainError):
    def __init__(self, message: str, *args: object) -> None:
        super().__init__(message, *args)
