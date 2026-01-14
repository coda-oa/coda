from typing import Any

from coda.contexts.fundingrequest.dto.commands import ExtraContactDto, ExtraInformationDto
from tests import domainfactory


def stepdata(extra_information: ExtraInformationDto | None = None) -> dict[str, Any]:
    extra_information = extra_information or ExtraInformationDto(
        request_remarks="remarks",
        extra_contact=ExtraContactDto.from_contact(domainfactory.fundingrequest_contact()),
    )

    return (
        extra_information.to_post_data(exclude={"extra_contact"})
        | extra_information.extra_contact.to_post_data()
    )
