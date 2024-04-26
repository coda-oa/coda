from datetime import date
from typing import cast

import pytest

from coda.publication import Published


def test__published_state__requires_date() -> None:
    with pytest.raises(ValueError):
        Published(date=cast(date, None))
