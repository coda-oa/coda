import pytest

from coda.apps.journals import services
from coda.domain.contract import PublisherId
from coda.domain.issn import Issn
from coda.domain.string import NonEmptyStr
from tests import modelfactory


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("00280836", "0028-0836"),
        ("123-45679", "1234-5679"),
    ],
)
def test__create_journal__stores_canonical_eissn(given: str, stored: str) -> None:
    publisher = modelfactory.publisher()

    journal_id = services.create(
        NonEmptyStr("Journal of Testing"), Issn(given), PublisherId(publisher.pk)
    )

    assert services.get_by_pk(journal_id).eissn == stored
    assert services.find_by_eissn(Issn(stored)) is not None
