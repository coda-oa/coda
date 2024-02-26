from coda.apps.journals.models import Journal


def get_by_id(id: int) -> Journal:
    return Journal.objects.get(pk=id)
