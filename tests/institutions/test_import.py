from io import StringIO
from pathlib import Path

import pytest

from coda.apps.institutions import services
from coda.apps.institutions.models import Institution

ordered_institutions_path = Path(__file__).parent / "test_institutions_ordered.csv"


@pytest.mark.django_db
def test__can_create_institutions_from_file() -> None:
    with Path(ordered_institutions_path).open() as file:
        services.import_from_file(StringIO(file.read()))

    institution_and_parent_names = [
        ("the-root", None),
        ("first-child", "the-root"),
        ("second-child", "the-root"),
        ("first-child-child", "first-child"),
        ("second-child-child", "second-child"),
    ]

    for name, parent_name in institution_and_parent_names:
        assert Institution.objects.filter(name=name, parent__name=parent_name).exists()


@pytest.mark.django_db
def test__uploading_same_list_twice__does_not_duplicate_institutions() -> None:
    with Path(ordered_institutions_path).open() as file:
        services.import_from_file(StringIO(file.read()))

    with Path(ordered_institutions_path).open() as file:
        services.import_from_file(StringIO(file.read()))

    assert Institution.objects.count() == 5
