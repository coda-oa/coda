from coda.apps.fundingrequests.models import FundingRequest as FundingRequestModel
from coda.apps.fundingrequests.models import Label
from coda.domain.color import Color
from coda.domain.fundingrequest import FundingRequestId


def label_create(name: str, color: Color) -> Label:
    return Label.objects.create(name=name, hexcolor=color.hex())


def label_bulk_get_or_create(label_names: set[str]) -> dict[str, Label]:
    existing_label_objects = Label.objects.filter(name__in=label_names).order_by("id")

    existing_labels = {}
    for label in existing_label_objects:
        if label.name not in existing_labels:
            existing_labels[label.name] = label

    labels_to_create = [
        Label(name=name, hexcolor="#007bff") for name in label_names if name not in existing_labels
    ]
    if labels_to_create:
        Label.objects.bulk_create(labels_to_create)
        created_label_names = [label_obj.name for label_obj in labels_to_create]
        newly_created = {
            label.name: label for label in Label.objects.filter(name__in=created_label_names)
        }
        existing_labels.update(newly_created)

    return existing_labels


def label_attach(funding_request: FundingRequestModel, label: Label) -> None:
    label.requests.add(funding_request)
    label.save()


def label_attach_bulk_by_id(funding_request_id: FundingRequestId, labels: list[Label]) -> None:
    through_model = FundingRequestModel.labels.through

    through_objects = [
        through_model(fundingrequest_id=funding_request_id, label_id=label.id) for label in labels
    ]

    through_model.objects.bulk_create(through_objects, ignore_conflicts=True)


def label_attach_bulk_many(request_labels: dict[FundingRequestId, list[Label]]) -> None:
    """Attach labels to multiple funding requests in a single bulk operation.

    Args:
        request_labels: Mapping of funding request ID to list of labels to attach

    Example:
        >>> labels = {
        ...     FundingRequestId(1): [label1, label2],
        ...     FundingRequestId(2): [label3],
        ... }
        >>> label_attach_bulk_many(labels)
    """
    if not request_labels:
        return

    through_model = FundingRequestModel.labels.through

    through_objects = [
        through_model(fundingrequest_id=fr_id, label_id=label.id)
        for fr_id, labels in request_labels.items()
        for label in labels
    ]

    through_model.objects.bulk_create(through_objects, ignore_conflicts=True)


def label_detach(funding_request: FundingRequestModel, label: Label) -> None:
    label.requests.remove(funding_request)
    label.save()
