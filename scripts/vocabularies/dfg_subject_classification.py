from pathlib import Path
from typing import Any

import polars as pl

from ._common import Concept, Vocabulary

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DFG_SUBJECT_CLASSIFICATION_PATH = (
    BASE_DIR / "resources" / "Fachsystematik_2024-2028_EN_20230526.xlsx"
)


def process_excel() -> pl.DataFrame:
    df = pl.read_excel(DFG_SUBJECT_CLASSIFICATION_PATH, read_options={"header_row": 2})
    df = (
        df.with_columns(
            pl.col("Subject area").alias("Subject area ID"),
            pl.col("__UNNAMED__1").alias("Subject area name"),
            pl.col("Review Board").str.replace("\n", " "),
            pl.col("__UNNAMED__3").alias("Subgroup").str.replace("\n", " "),
            pl.col("__UNNAMED__4").alias("Group").str.replace("\n", " "),
        )
        .with_columns(
            pl.col("Subgroup").fill_null(strategy="forward"),
            pl.col("Group").fill_null(strategy="forward"),
            pl.col("Review Board").fill_null(strategy="forward"),
        )
        .with_columns(
            pl.col("Review Board").str.slice(0, 4).str.strip_chars().alias("Review Board ID"),
            pl.col("Review Board").str.slice(4).str.strip_chars().alias("Review Board name"),
            pl.col("Subgroup").str.slice(0, 2).str.strip_chars().alias("Subgroup ID"),
            pl.col("Subgroup").str.slice(3).str.strip_chars().alias("Subgroup name"),
            pl.col("Group").str.slice(0, 1).str.strip_chars().alias("Group ID"),
            pl.col("Group").str.slice(2).str.strip_chars().alias("Group name"),
        )
        .filter(pl.col("Subject area ID") != "Subject area")
        .drop(
            [
                "Review Board",
                "Subject area",
                "Subgroup",
                "Group",
                "__UNNAMED__1",
                "__UNNAMED__3",
                "__UNNAMED__4",
            ],
            strict=False,
        )
    )
    return df


def parse_vocabulary() -> Vocabulary:
    df = process_excel().sort("Group ID", "Subgroup ID", "Review Board ID", "Subject area ID")
    groups = df.select("Group ID", "Group name").unique(keep="first", maintain_order=True)
    group_concepts = [group(df, row) for row in groups.iter_rows(named=True)]

    v = Vocabulary(
        name="DFG Subject Classification",
        version="2024-2028",
        concepts=group_concepts,
    )
    return v


def group(df: pl.DataFrame, group: dict[str, Any]) -> Concept:
    group_id = group["Group ID"]
    group_name = group["Group name"]
    subgroup_concepts = subgroups_for_group(df, group_id)
    return Concept(
        id=group_id,
        name=group_name,
        description="",
        subconcepts=subgroup_concepts,
    )


def subgroups_for_group(df: pl.DataFrame, group_id: str) -> list[Concept]:
    matching_subgroups = (
        df.filter(pl.col("Group ID") == group_id)
        .select("Subgroup ID", "Subgroup name")
        .unique(keep="first", maintain_order=True)
    )
    subgroup_concepts = [
        Concept(
            id=row["Subgroup ID"],
            name=row["Subgroup name"],
            description="",
            subconcepts=review_boards_for_subgroup(df, row["Subgroup ID"]),
        )
        for row in matching_subgroups.iter_rows(named=True)
    ]

    return subgroup_concepts


def review_boards_for_subgroup(df: pl.DataFrame, subgroup_id: str) -> list[Concept]:
    matching_review_boards = (
        df.filter(pl.col("Subgroup ID") == subgroup_id)
        .select("Review Board ID", "Review Board name")
        .unique(keep="first", maintain_order=True)
    )
    review_board_concepts = [
        Concept(
            id=row["Review Board ID"],
            name=row["Review Board name"],
            description="",
            subconcepts=subject_for_review_board(df, row["Review Board ID"]),
        )
        for row in matching_review_boards.iter_rows(named=True)
    ]

    return review_board_concepts


def subject_for_review_board(df: pl.DataFrame, review_board_id: str) -> list[Concept]:
    matching_subjects = df.filter(pl.col("Review Board ID") == review_board_id).select(
        "Subject area ID", "Subject area name"
    )
    subject_concepts = [
        Concept(
            id=row["Subject area ID"],
            name=row["Subject area name"],
            description="",
            subconcepts=[],
        )
        for row in matching_subjects.iter_rows(named=True)
    ]

    return subject_concepts
