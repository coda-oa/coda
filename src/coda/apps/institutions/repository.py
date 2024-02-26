from coda.apps.institutions.models import Institution


def get_by_id(id: int) -> Institution:
    return Institution.objects.get(pk=id)
