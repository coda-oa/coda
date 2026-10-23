"""Factories building statistics facts with spec defaults; override per test."""

import itertools
from datetime import date
from decimal import Decimal

from coda.contexts.statistics.dto import FundingSourceRef, InstitutionRef, RequestFact

_request_ids = itertools.count(1)
_publication_ids = itertools.count(100)


def make_fact(**overrides: object) -> RequestFact:
    defaults: dict[str, object] = {
        "request_id": next(_request_ids),
        "publication_id": next(_publication_ids),
        "request_date": date(2026, 5, 1),
        "title": "A funded publication",
        "subject_area": None,
        "publication_type": None,
        "publication_form": "article",
        "license": "cc-by",
        "open_access_type": "gold",
        "journal": None,
        "publisher": None,
        "contracts": (),
        "funders": (),
        "institutions": (),
        "no_corresponding_author": False,
        "paid_out_by_cost_type": {},
        "paid_out_total": Decimal(0),
        "funded_by": {},
        "unassigned": Decimal(0),
        "invoices_without_rate": 0,
        "unconvertible_invoice_ids": (),
        "has_invoice": True,
    }
    return RequestFact(**{**defaults, **overrides})  # type: ignore[arg-type]


def institution(name: str) -> InstitutionRef:
    return InstitutionRef(name=name)


def source(name: str) -> FundingSourceRef:
    return FundingSourceRef(name=name)
