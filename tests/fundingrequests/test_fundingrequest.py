import datetime

import pytest

from tests import modelfactory


@pytest.mark.django_db
def test__fundingrequest__has_valid_id_pattern() -> None:
    request = modelfactory.fundingrequest()

    split_id = request.request_id.split("-")
    uuid_component = len(split_id[1])
    date_component = datetime.date(*map(int, split_id[2:]))
    assert split_id[0] == "coda"
    assert uuid_component == 8
    assert date_component == request.created_at.date()
