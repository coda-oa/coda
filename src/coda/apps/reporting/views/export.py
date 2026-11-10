"""CSV export of one statistics dimension's complete value set (plan §4–§7).

One file per dimension section: the unbounded grouping under the page's
current filters, with no top-10 cut and no "Other" fold, plus the
comparison period's raw values when compare is on. The form construction,
the facts pipeline and the comparison resolution are the page's own
(shared builder and helper), so an export right after a page render with
the same filters answers from the cached fact sets.
"""

from io import StringIO

import polars as pl
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.utils import timezone
from django.views.decorators.http import require_GET

from coda.apps.contracts.models import Contract
from coda.apps.fundingrequests.forms import FundingRequestListFilterForm
from coda.apps.fundingrequests.models import Label
from coda.apps.preferences.models import GlobalPreferences
from coda.apps.reporting import factcache
from coda.apps.reporting.views.page import facts_builder, resolve_comparison_period
from coda.contexts.statistics import aggregation
from coda.contexts.statistics.dimensions import Dimension, by_id
from coda.contexts.statistics.dto import Grouping, GroupRow, Measure, RequestFact
from coda.domain.money import Currency

CSV_ENCODING = "utf-8-sig"
CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
MISSING_DATES_MESSAGE = "Both dates are required."


@login_required
@require_GET
def csv_export(request: HttpRequest, dimension_id: str) -> HttpResponse:
    """The section's complete value set as a CSV download (plan §7).

    Date errors mirror the page's contract: an invalid or missing period is
    HTTP 400 with the form's error text, never a CSV body with a sentence
    in it. The compare toggle gates exactly as on the page
    (``compare == "1"``). An unresolvable comparison period degrades to
    current-period columns."""
    try:
        dimension = by_id(dimension_id)
    except KeyError:
        raise Http404(f"unknown statistics dimension: {dimension_id!r}") from None

    filter_form = FundingRequestListFilterForm(
        request.GET,
        contracts=list(Contract.objects.all()),
        labels=list(Label.used_labels()),
        vocabularies=GlobalPreferences.preloaded(),
        include_labels_widget=True,
    )
    filter_form.is_valid()
    date_errors = filter_form.errors.get("date_range")
    if date_errors:
        return HttpResponseBadRequest(str(date_errors[0]))
    if filter_form.cleaned_data.get("date_range") is None:
        # A bare GET (hand-typed or bookmarked URL) would silently export an
        # unbounded period, never the window the user saw on the page. The
        # page redirects to the default period. The export refuses instead.
        return HttpResponseBadRequest(MISSING_DATES_MESSAGE)

    home_currency = GlobalPreferences.get_home_currency()
    criteria, _sort_order = filter_form.search_criteria()
    build_facts = facts_builder(filter_form, criteria, home_currency)
    facts = factcache.facts_for(request.GET, home_currency, build_facts)

    compare_requested = request.GET.get("compare") == "1"
    comparison_facts: tuple[RequestFact, ...] | None = None
    if compare_requested:
        comparison_period, comparison_error = resolve_comparison_period(
            filter_form, compare_requested=True
        )
        if comparison_error is None and comparison_period is not None:
            comparison_facts = factcache.facts_for(
                request.GET,
                home_currency,
                build_facts,
                comparison_period=comparison_period,
            )

    grouping = aggregation.group_by(facts, dimension, top_n=None)
    comparison_grouping = (
        aggregation.group_by(comparison_facts, dimension, top_n=None)
        if comparison_facts is not None
        else None
    )
    timestamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
    response = HttpResponse(
        dimension_csv(dimension, grouping, comparison_grouping, currency=home_currency),
        content_type=CSV_CONTENT_TYPE,
    )
    response["Content-Disposition"] = (
        f'attachment; filename="{dimension.id}_export_{timestamp}.csv"'
    )
    return response


def _measure_columns(dimension: Dimension) -> tuple[str, ...]:
    """The export's value columns: one per measure the dimension supports,
    with the money column uniformly named ``amount`` (plan §6). Spend vs
    funded-by is the page's display distinction; the file carries numbers."""
    return tuple(
        "publications" if measure is Measure.PUBLICATIONS else "amount"
        for measure in dimension.measures()
    )


def dimension_csv(
    dimension: Dimension,
    grouping: Grouping,
    comparison: Grouping | None = None,
    *,
    currency: Currency,
) -> bytes:
    """The grouping as CSV (plan §6): ``;``-separated, ``utf-8-sig``-encoded,
    rows in the grouping's rank order (the table's order), UNKNOWN and
    UNASSIGNED included. The ``currency`` column follows the ``label``
    column when the dimension has a money measure and holds the home
    currency's code on every row, comparison cells included: one page-wide
    currency per ADR-0003, so the code is file-level, not per period. A row
    absent from the prior period leaves the comparison cells blank, which is
    distinguishable from a zero, a real prior-period value. Label cells are
    written verbatim, like every other export in this project; a label
    starting with ``=``, ``+``, ``-`` or ``@`` can read as a formula when
    the file opens in a spreadsheet."""
    columns = _measure_columns(dimension)
    has_money = "amount" in columns
    header = ["label", *(["currency"] if has_money else []), *columns]
    prior_by_label: dict[str, GroupRow] = {}
    if comparison is not None:
        prior_by_label = {row.label: row for row in comparison.rows}
        header += [f"comparison_{column}" for column in columns]

    def cells(row: GroupRow) -> dict[str, str | None]:
        values: dict[str, str | None] = {"label": row.label}
        if has_money:
            values["currency"] = currency.code
        if "publications" in columns:
            values["publications"] = str(row.publications)
        if has_money:
            values["amount"] = str(row.amount)
        if comparison is not None:
            prior = prior_by_label.get(row.label)
            if "publications" in columns:
                values["comparison_publications"] = str(prior.publications) if prior else None
            if has_money:
                values["comparison_amount"] = str(prior.amount) if prior else None
        return values

    frame = pl.DataFrame(
        [cells(row) for row in grouping.rows],
        schema={column: pl.String for column in header},
    )
    buffer = StringIO()
    frame.write_csv(buffer, separator=";")
    return buffer.getvalue().encode(CSV_ENCODING)
