"""``QualityAnnotation`` + the ``duplicate_row``-only first producer (M1A.5).

Quality is a **cross-record** conclusion, versioned by detector, kept outside the
source record and its immutability hash. The **first producer emits only
``duplicate_row``** (``PROPOSAL.md`` decision D): assembly needs duplicate
detection as an input and that is on the immediate path; the contamination
detector (``clean`` / ``suspicious`` / ``rejected`` — the GA/NC-boilerplate case)
is deferred until a corpus at risk is ingested. Suspicious rows are **never
deleted** — duplicates stay in the immutable core; this annotation only records
the relationship.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Iterable

from .provenance import (
    ArtifactType,
    DerivedArtifactProvenance,
    Evidence,
    source_record_inputs,
)

if TYPE_CHECKING:
    from open_us_law_coverage.source_record import CanonicalSourceRecord


PRODUCER_NAME = "quality_duplicate_row"
PRODUCER_VERSION = "1"


class QualityStatus(StrEnum):
    UNKNOWN = "unknown"
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    REJECTED = "rejected"


class QualityFlag(StrEnum):
    DUPLICATE_ROW = "duplicate_row"


@dataclass(frozen=True, slots=True)
class QualityAnnotation:
    provenance: DerivedArtifactProvenance
    quality_status: QualityStatus
    quality_flags: tuple[QualityFlag, ...] = field(default_factory=tuple)
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)


def detect_duplicate_rows(
    records: Iterable["CanonicalSourceRecord"],
    *,
    producer_version: str = PRODUCER_VERSION,
) -> list[QualityAnnotation]:
    """Flag byte-identical rows within the given scope.

    The caller decides scope (typically one identity group or one file). Rows
    whose ``raw_text_hash`` collides with at least one other row in the batch get
    a ``duplicate_row`` flag; every other row gets a clean, flagless annotation
    (``quality_status = unknown`` — this producer does not certify ``clean``).
    Null-text rows are never duplicates of each other (there is no content to
    address), matching ``raw_text_hash is None``.

    Order of the returned annotations follows the input order.
    """
    materialized = list(records)
    by_hash: dict[str, list[str]] = defaultdict(list)
    for rec in materialized:
        if rec.raw_text_hash is not None:
            by_hash[rec.raw_text_hash].append(rec.source_record_id)

    out: list[QualityAnnotation] = []
    for rec in materialized:
        provenance = DerivedArtifactProvenance.build(
            ArtifactType.QUALITY_ANNOTATION,
            source_record_inputs([rec.source_record_id]),
            PRODUCER_NAME,
            producer_version,
        )
        siblings = (
            by_hash.get(rec.raw_text_hash, []) if rec.raw_text_hash is not None else []
        )
        is_dup = len(siblings) > 1
        flags = (QualityFlag.DUPLICATE_ROW,) if is_dup else ()
        evidence = (
            (
                Evidence(
                    "byte_identical_text",
                    f"raw_text_hash shared by {len(siblings)} rows in scope: "
                    + ", ".join(sorted(siblings)),
                    confidence=1.0,
                ),
            )
            if is_dup
            else ()
        )
        out.append(
            QualityAnnotation(
                provenance=provenance,
                quality_status=QualityStatus.UNKNOWN,
                quality_flags=flags,
                evidence=evidence,
            )
        )
    return out
