import pytest

from typing import cast

from coda.apps.exports.services.filter_form import (
    FilterCleanedData,
    FundingRequestFilterForm,
    build_filters_from_cleaned_data,
    form_error_lines,
)
from coda.apps.fundingrequests.fundingrequest_query import (
    PaymentStatus as FundingRequestPaymentStatus,
)
from coda.apps.invoices import funding_source_repository
from coda.contexts.fundingrequest.services.labels import label_create
from coda.domain.author import InstitutionId
from coda.domain.color import Color
from coda.domain.finance.invoice import FundingSourceId
from coda.domain.fundingrequest.fundingrequest import PaymentMethod
from coda.domain.fundingrequest.review import ReviewResult
from coda.domain.publication import OpenAccessType
from tests import domainfactory, modelfactory


def _valid_base() -> dict[str, str]:
    return {"period_start": "2026-01-01", "period_end": "2026-01-31"}


def test__minimal_valid_post__validating__is_valid() -> None:
    assert FundingRequestFilterForm(_valid_base()).is_valid()


def test__post_without_period_dates__validating__is_invalid() -> None:
    form = FundingRequestFilterForm({})
    assert not form.is_valid()
    assert "period_start" in form.errors
    assert "period_end" in form.errors


def test__malformed_period_start_date__validating__is_invalid() -> None:
    data = {**_valid_base(), "period_start": "01.01.2026"}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "period_start" in form.errors


def test__invalid_decimal_separator__validating__is_invalid() -> None:
    data = {**_valid_base(), "decimal_separator": "x"}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "decimal_separator" in form.errors


def test__post_without_decimal_separator__validating__cleans_to_empty_string() -> None:
    form = FundingRequestFilterForm(_valid_base())
    assert form.is_valid()
    assert form.cleaned_data["decimal_separator"] == ""


def test__post_with_search_term__validating__keeps_search_term_in_cleaned_data() -> None:
    data = {**_valid_base(), "search_term": "hello"}
    form = FundingRequestFilterForm(data)
    assert form.is_valid()
    assert form.cleaned_data["search_term"] == "hello"


def test__invalid_processing_status__validating__is_invalid() -> None:
    data = {**_valid_base(), "processing_status": ["not_a_status"]}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "processing_status" in form.errors


def test__valid_processing_status__validating__coerces_to_enum() -> None:
    data = {**_valid_base(), "processing_status": [ReviewResult.Approved.value]}
    form = FundingRequestFilterForm(data)
    assert form.is_valid()
    assert form.cleaned_data["processing_status"] == [ReviewResult.Approved]


def test__post_without_processing_status__validating__cleans_to_empty_list() -> None:
    form = FundingRequestFilterForm(_valid_base())
    assert form.is_valid()
    assert form.cleaned_data["processing_status"] == []


def test__invalid_payment_status__validating__is_invalid() -> None:
    data = {**_valid_base(), "payment_status": ["not_a_status"]}
    assert not FundingRequestFilterForm(data).is_valid()


def test__valid_payment_status__validating__coerces_to_enum() -> None:
    data = {**_valid_base(), "payment_status": [FundingRequestPaymentStatus.Paid.value]}
    form = FundingRequestFilterForm(data)
    assert form.is_valid()
    assert form.cleaned_data["payment_status"] == [FundingRequestPaymentStatus.Paid]


def test__invalid_payment_method__validating__is_invalid() -> None:
    data = {**_valid_base(), "payment_methods": ["not_a_method"]}
    assert not FundingRequestFilterForm(data).is_valid()


def test__valid_payment_method__validating__coerces_to_enum() -> None:
    first = next(iter(PaymentMethod))
    data = {**_valid_base(), "payment_methods": [first.value]}
    form = FundingRequestFilterForm(data)
    assert form.is_valid()
    assert form.cleaned_data["payment_methods"] == [first]


def test__invalid_open_access_type__validating__is_invalid() -> None:
    data = {**_valid_base(), "open_access_type": ["not_an_oat"]}
    assert not FundingRequestFilterForm(data).is_valid()


def test__valid_open_access_type__validating__coerces_to_enum() -> None:
    first = next(iter(OpenAccessType))
    data = {**_valid_base(), "open_access_type": [first.value]}
    form = FundingRequestFilterForm(data)
    assert form.is_valid()
    assert form.cleaned_data["open_access_type"] == [first]


def test__invalid_publication_state__validating__is_invalid() -> None:
    data = {**_valid_base(), "publication_states": ["not_a_state"]}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "publication_states" in form.errors


def test__valid_publication_states__validating__keeps_values_in_cleaned_data() -> None:
    data = {**_valid_base(), "publication_states": ["Published"]}
    form = FundingRequestFilterForm(data)
    assert form.is_valid()
    assert form.cleaned_data["publication_states"] == ["Published"]


def test__invalid_publication_type__validating__is_invalid() -> None:
    data = {**_valid_base(), "publication_type": "not_a_type"}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "publication_type" in form.errors


@pytest.mark.django_db
def test__invalid_label_id__validating__is_invalid() -> None:
    data = {**_valid_base(), "labels": ["999999"]}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "labels" in form.errors


@pytest.mark.django_db
def test__valid_label_id__validating__coerces_to_label_model() -> None:
    label = label_create("Alpha", Color.from_rgb(255, 0, 0))
    data = {**_valid_base(), "labels": [str(label.pk)]}
    form = FundingRequestFilterForm(data)
    assert form.is_valid()
    assert [item.pk for item in form.cleaned_data["labels"]] == [label.pk]


@pytest.mark.django_db
def test__invalid_exclude_label_id__validating__is_invalid() -> None:
    data = {**_valid_base(), "exclude_labels": ["999999"]}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "exclude_labels" in form.errors


@pytest.mark.django_db
def test__invalid_contract_id__validating__is_invalid() -> None:
    data = {**_valid_base(), "contract_name": "999999"}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "contract_name" in form.errors


@pytest.mark.django_db
def test__valid_contract_id__validating__coerces_to_contract_model() -> None:
    contract = modelfactory.contract()
    data = {**_valid_base(), "contract_name": str(contract.pk)}
    form = FundingRequestFilterForm(data)
    assert form.is_valid()
    assert form.cleaned_data["contract_name"].pk == contract.pk


@pytest.mark.django_db
def test__invalid_funding_source_id__validating__is_invalid() -> None:
    data = {**_valid_base(), "funding_source": "999999"}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "funding_source" in form.errors


@pytest.mark.django_db
def test__non_budget_funding_source__validating__is_invalid() -> None:
    institution = modelfactory.institution()
    source = domainfactory.split_source(InstitutionId(institution.pk), institution.name)
    source.id = funding_source_repository.create(source)
    data = {**_valid_base(), "funding_source": str(source.id)}
    form = FundingRequestFilterForm(data)
    assert not form.is_valid()
    assert "funding_source" in form.errors


@pytest.mark.django_db
def test__budget_funding_source__validating__coerces_to_model() -> None:
    budget_model = modelfactory.budget(name="Form Test Budget")
    budget_source = domainfactory.budget(FundingSourceId(budget_model.pk))
    budget_source.id = funding_source_repository.create(budget_source)
    data = {**_valid_base(), "funding_source": str(budget_model.pk)}
    form = FundingRequestFilterForm(data)
    assert form.is_valid()
    assert form.cleaned_data["funding_source"].pk == budget_model.pk


@pytest.mark.django_db
def test__fully_filled_valid_form__serializing__matches_persisted_filter_format() -> None:
    label = label_create("Serializable Label", Color.from_rgb(1, 2, 3))
    contract = modelfactory.contract()
    form = FundingRequestFilterForm(
        {
            "period_start": "2026-01-01",
            "period_end": "2026-03-31",
            "decimal_separator": ",",
            "search_term": "hello",
            "processing_status": [
                ReviewResult.Approved.value,
                ReviewResult.Rejected.value,
            ],
            "labels": [str(label.pk)],
            "contract_name": str(contract.pk),
        }
    )
    assert form.is_valid()
    assert build_filters_from_cleaned_data(cast(FilterCleanedData, form.cleaned_data)) == {
        "period_start": "2026-01-01",
        "period_end": "2026-03-31",
        "decimal_separator": ",",
        "search_term": "hello",
        "processing_status": f"{ReviewResult.Approved.value},{ReviewResult.Rejected.value}",
        "labels": str(label.pk),
        "contract_name": str(contract.pk),
    }


def test__valid_form_with_only_period_dates__serializing__omits_empty_optionals() -> None:
    form = FundingRequestFilterForm(_valid_base())
    assert form.is_valid()
    assert build_filters_from_cleaned_data(cast(FilterCleanedData, form.cleaned_data)) == {
        "period_start": "2026-01-01",
        "period_end": "2026-01-31",
    }


def test__missing_required_fields__building_error_lines__uses_readable_labels() -> None:
    form = FundingRequestFilterForm({})
    lines = form_error_lines(form)

    assert [line.label for line in lines] == ["Period Start", "Period End"]
    assert lines[0].errors == ["This field is required."]
    assert all(isinstance(line.errors, list) for line in lines)


@pytest.mark.django_db
def test__invalid_funding_source__building_error_lines__uses_funding_source_label() -> None:
    form = FundingRequestFilterForm({**_valid_base(), "funding_source": "999999"})
    lines = form_error_lines(form)

    assert [line.label for line in lines] == ["Funding Source"]
