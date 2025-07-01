from io import BytesIO, StringIO
from typing import Any

import polars as pl

from coda.apps.institutions.models import Institution


def import_from_file(file: BytesIO | StringIO) -> None:
    df = pl.read_csv(file, separator=";", has_header=True)

    institutions = [
        Institution.objects.get_or_create(name=name)[0] for name in df.get_column("name")
    ]

    for i, institution in enumerate(institutions):
        parent_row_number_in_file = df.row(i, named=True).get("parent")
        if parent_row_number_in_file is not None:
            parent_name: str = _parent_row(df, parent_row_number_in_file).get("name", "")
            parent = Institution.objects.get(name=parent_name)
            institution.parent = parent
            institution.save()


def _parent_row(df: pl.DataFrame, parent_row_number_in_file: int) -> dict[str, Any]:
    return df.row(_parent_row_number(parent_row_number_in_file), named=True)


# NOTE: HEADER_OFFSET is 2 because the first row is the header and we start counting numbers from 0 after the header
HEADER_OFFSET = 2


def _parent_row_number(parent_row_number_in_file: int) -> int:
    return parent_row_number_in_file - HEADER_OFFSET
