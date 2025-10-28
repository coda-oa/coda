class CannotProcessField(Exception):
    """Base exception raised when a processor cannot handle a field."""

    pass


class FieldAlreadyExists(CannotProcessField):
    """Raised when a field already exists in the data."""

    pass


class ValidationFailed(Exception):
    """Raised when field validation fails during processing."""

    pass
