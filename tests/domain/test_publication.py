from datetime import date
from typing import cast

import pytest

from coda.publication import Published


def test__published_state__requires_at_least_one_date() -> None:
    with pytest.raises(ValueError):
        Published(online=cast(date, None), print=cast(date, None))
