from collections.abc import Iterable
from typing import Any

from coda.contexts.fundingrequest.dto.commands import ExternalFundingDto, PaymentDto
from coda.apps.htmx_components.converters import to_htmx_formset_data
from tests import domainfactory


def stepdata(
    payment_dto: PaymentDto | None = None, funding_dtos: Iterable[ExternalFundingDto] | None = None
) -> dict[str, Any]:
    payment_dto = payment_dto or PaymentDto.from_payment(domainfactory.payment())
    funding_dtos = (
        list(funding_dtos)
        if funding_dtos is not None
        else [ExternalFundingDto.from_external_funding(domainfactory.external_funding())]
    )

    fundings = to_htmx_formset_data(funding_dtos)
    return fundings | payment_dto.to_post_data()
