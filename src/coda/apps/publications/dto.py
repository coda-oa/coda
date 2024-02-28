from typing import TypedDict


class LinkDto(TypedDict):
    link_type: int
    link_value: str


class PublicationDto(TypedDict):
    title: str
    publication_state: str
    publication_date: str
    links: list[LinkDto]
    journal: int
