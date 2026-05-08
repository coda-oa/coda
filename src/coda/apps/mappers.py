def prefixed(prefix: str, field: str) -> str:
    return f"{prefix}__{field}" if prefix else field
