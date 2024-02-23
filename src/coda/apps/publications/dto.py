from typing import TypedDict


class PublicationDto(TypedDict):
    title: str
    journal: int
    publication_state: str
    publication_date: str
