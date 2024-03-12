from coda.apps.journals.models import Journal


def get_by_pk(pk: int) -> Journal:
    return Journal.objects.get(pk=pk)
