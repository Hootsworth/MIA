# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
"""Reject train/validation/test partitions that share identity groups."""


def validate_grouped_splits(splits: dict[str, list[dict]], *, group_fields=("author_id", "source_group", "duplicate_group")):
    names = ("train", "validation", "test")
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            for field in group_fields:
                a = {row[field] for row in splits.get(left, []) if row.get(field) is not None}
                b = {row[field] for row in splits.get(right, []) if row.get(field) is not None}
                overlap = a & b
                if overlap:
                    raise ValueError(f"leakage: {field} shared between {left} and {right}: {sorted(overlap)}")
    return True
