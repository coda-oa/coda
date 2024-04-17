import re


class AuthorList(list[str]):
    @classmethod
    def from_str(cls, authors: str) -> "AuthorList":
        authors = cls._insert_missing_space(authors)
        authors = cls._replace_broken_umlaute(authors)
        author_lines = authors.strip().splitlines()
        reverse = "," in authors and ";" in authors
        return cls(
            author
            for line in author_lines
            for author in cls._parse_line(line, reverse_names=reverse)
            if author
        )

    @staticmethod
    def _parse_line(line: str, /, reverse_names: bool) -> list[str]:
        if reverse_names:
            split_authors_by_semicolon = map(str.strip, line.split(";"))
            split_names_by_comma = [x.split(",") for x in split_authors_by_semicolon]
            reversed_names = [reversed(x) for x in split_names_by_comma]
            split_authors = [" ".join(x).strip() for x in reversed_names]
        else:
            sep = "," if "," in line else ";"
            line = line.replace(", and ", sep).replace(" and ", sep)
            split_authors = [*map(str.strip, line.split(sep))]

        return split_authors

    @staticmethod
    def _insert_missing_space(author: str) -> str:
        return re.sub(r"([a-z])([A-Z])", r"\1 \2", author)

    @staticmethod
    def _replace_broken_umlaute(author: str) -> str:
        return author.replace(" ̈u", "ü").replace(" ̈o", "ö").replace(" ̈a", "ä")

    def __str__(self) -> str:
        return ", ".join(self)
