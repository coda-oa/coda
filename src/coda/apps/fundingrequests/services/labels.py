from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.color import Color


def label_create(name: str, color: Color) -> Label:
    return Label.objects.create(name=name, hexcolor=color.hex())


def label_attach(funding_request: FundingRequestModel, label: Label) -> None:
    label.requests.add(funding_request)
    label.save()


def label_detach(funding_request: FundingRequestModel, label: Label) -> None:
    label.requests.remove(funding_request)
    label.save()
