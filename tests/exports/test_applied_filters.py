import pytest

from coda.apps.exports.services.filter_display import build_applied_filters


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("filters", "label"),
    [
        ({"processing_status": "approved"}, "Processing Status"),
        ({"payment_methods": "direct"}, "Payment Methods"),
        ({"open_access_type": "Gold"}, "Open Access Type"),
        ({"publication_states": "Published"}, "Publication States"),
        ({"labels": "999999"}, "Labels"),
        ({"exclude_labels": "999999"}, "Excluded Labels"),
        ({"payment_status": "paid"}, "Payment Status"),
        ({"publication_type": "article"}, "Publication Type"),
        ({"contract_name": "999999"}, "Contracts"),
        ({"funding_source": "999999"}, "Funding Source"),
        ({"decimal_separator": ","}, "Decimal Separator"),
        ({"period_start": "2024-01-01", "period_end": "2024-12-31"}, "Period"),
    ],
)
def test__single_filter_criteria__building_applied_filters__uses_human_readable_label(
    filters: dict[str, str], label: str
) -> None:
    applied = build_applied_filters(filters)

    assert [f.label for f in applied] == [label]


def test__unknown_filter_key__building_applied_filters__produces_no_filters() -> None:
    assert build_applied_filters({"some_unknown_key": "x"}) == []
