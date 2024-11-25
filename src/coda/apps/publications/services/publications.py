from coda.apps.publications.repositories import publication_repository
from coda.publication import Publication, PublicationId


def publication_create(publication: Publication) -> PublicationId:
    return publication_repository.save(publication)


def publication_update(publication: Publication) -> None:
    publication_repository.save(publication)
