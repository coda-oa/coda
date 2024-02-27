from typing import TypedDict


class LinkDto(TypedDict):
    link_type_id: int
    value: str


class PublicationDto(TypedDict):
    title: str
    publication_state: str
    publication_date: str
    links: list[LinkDto]
