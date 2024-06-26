from pathlib import Path
from typing import Any

import polars as pl

from ._common import Concept, Vocabulary

BASE_DIR = Path(__file__).resolve().parent.parent.parent

DFG_SUBJECT_CLASSIFICATION_PATH = (
    BASE_DIR / "resources" / "Fachsystematik_2024-2028_EN_20230526.xlsx"
)


def process_excel() -> pl.DataFrame:
    df = pl.read_excel(DFG_SUBJECT_CLASSIFICATION_PATH, read_options={"skip_rows": 2})
    return (
        df.with_columns(
            pl.col("Subject area").alias("Subject area ID"),
            pl.col("_duplicated_0").alias("Subject area name"),
            pl.col("_duplicated_1").alias("Subgroup").str.replace("\n", " "),
            pl.col("_duplicated_2").alias("Group").str.replace("\n", " "),
        )
        .with_columns(
            pl.col("Subgroup").fill_null(strategy="forward"),
            pl.col("Group").fill_null(strategy="forward"),
        )
        .with_columns(
            pl.col("Subgroup").str.slice(0, 2).str.strip_chars().alias("Subgroup ID"),
            pl.col("Subgroup").str.slice(3).str.strip_chars().alias("Subgroup name"),
            pl.col("Group").str.slice(0, 1).str.strip_chars().alias("Group ID"),
            pl.col("Group").str.slice(2).str.strip_chars().alias("Group name"),
        )
        .filter(pl.col("Subject area ID") != "Subject area")
        .drop(
            [
                "Subject area",
                "Subgroup",
                "Group",
                "_duplicated_0",
                "_duplicated_1",
                "_duplicated_2",
                "_duplicated_3",
            ]
        )
    )


def parse_vocabulary() -> Vocabulary:
    df = process_excel().sort("Group ID", "Subgroup ID", "Subject area ID")
    groups = df.select("Group ID", "Group name").unique(keep="first", maintain_order=True)
    group_concepts = [group(df, row) for row in groups.iter_rows(named=True)]

    return Vocabulary(
        name="DFG Subject Classification",
        version="2024-2028",
        concepts=group_concepts,
    )


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
            subconcepts=subjects_for_subgroup(df, row["Subgroup ID"]),
        )
        for row in matching_subgroups.iter_rows(named=True)
    ]

    return subgroup_concepts


def subjects_for_subgroup(df: pl.DataFrame, subgroup_id: str) -> list[Concept]:
    matching_subjects = df.filter(pl.col("Subgroup ID") == subgroup_id).select(
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
