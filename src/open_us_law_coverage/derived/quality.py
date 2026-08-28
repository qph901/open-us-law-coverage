"""``QualityAnnotation`` + the ``duplicate_row``-only first producer (M1A.5).

Quality is a **cross-record** conclusion, versioned by detector, kept outside the
source record and its immutability hash. The **first producer emits only
``duplicate_row``** (``PROPOSAL.md`` decision D): assembly needs duplicate
detection as an input and that is on the immediate path; the contamination
detector (``clean`` / ``suspicious`` / ``rejected`` — the GA/NC-boilerplate case)
is deferred until a corpus at risk is ingested. Suspicious rows are **never
deleted** — duplicates stay in the immutable core; this annotation only records
the relationship.

**Scope is one candidate identity group, never a whole file** (M1A.5 review B1).
``duplicate_row`` means "same bytes *within the candidate identity group*," never
"same legal identity" — CA proves identical bytes routinely span *distinct*
provisions (``[Reserved]``, ``[Repealed]``, reusable boilerplate; see
``reports/M0.5B3_ca_abstraction.md``), so a corpus/file scope would fabricate
duplicate edges across unrelated law.

The provenance is designed so a conclusion is fully reproducible from its declared
inputs. A detector run over a group is a first-class **scope artifact**
(:class:`DuplicateScope`), content-addressed by the *complete* member set. Each
per-record :class:`QualityAnnotation` names two inputs — the scope artifact and
its own target record — so:

* changing the sibling set changes the scope id and therefore every conclusion's
  ``artifact_id`` (the recompute frontier is complete), and
* two records in one scope never collide (the target ``source_record`` edge
  differs), so one ``artifact_id`` can never name two different conclusions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Iterable

from .provenance import (
    ArtifactInput,
    ArtifactType,
    DerivedArtifactProvenance,
    Evidence,
    InputType,
    assign_payload_hash,
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
class DuplicateScope:
    """A duplicate-detector run over exactly one candidate identity group.

    Content-addressed by the **complete member set** (its provenance edges are the
    sorted ``source_record`` ids of every member), so the scope id is stable under
    reordering but changes the instant a member is added or removed. Per-record
    :class:`QualityAnnotation`\\ s name this scope as an input, which is what gives
    every conclusion a complete recompute frontier.
    """

    provenance: DerivedArtifactProvenance
    member_source_record_ids: tuple[str, ...]
    payload_hash: str = ""
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.provenance.artifact_type != ArtifactType.DUPLICATE_SCOPE:
            raise ValueError(
                f"DuplicateScope provenance must be artifact_type "
                f"{ArtifactType.DUPLICATE_SCOPE}, got {self.provenance.artifact_type}"
            )
        members = self.member_source_record_ids
        if len(members) == 0:
            raise ValueError("a DuplicateScope must have at least one member")
        if len(set(members)) != len(members):
            raise ValueError(f"duplicate scope members are not allowed: {members}")
        if tuple(sorted(members)) != members:
            raise ValueError(
                f"member_source_record_ids must be sorted (canonical), got {members}"
            )
        if set(self.provenance.source_record_ids()) != set(members):
            raise ValueError(
                "member_source_record_ids must equal the provenance source_record "
                f"inputs (members={sorted(members)}, "
                f"provenance={sorted(set(self.provenance.source_record_ids()))})"
            )
        assign_payload_hash(
            self,
            ArtifactType.DUPLICATE_SCOPE,
            {
                "member_source_record_ids": list(members),
                "evidence": list(self.evidence),
            },
        )


@dataclass(frozen=True, slots=True)
class QualityAnnotation:
    """One record's quality conclusion within a :class:`DuplicateScope`.

    ``target_source_record_id`` is the row this conclusion is about; the same id is
    also a ``source_record`` provenance edge, alongside the scope-artifact edge.
    ``quality_status`` stays ``unknown`` (this producer certifies no overall
    cleanliness); the **flag** is the load-bearing signal downstream consumers read.
    """

    provenance: DerivedArtifactProvenance
    target_source_record_id: str
    quality_status: QualityStatus
    quality_flags: tuple[QualityFlag, ...] = field(default_factory=tuple)
    payload_hash: str = ""
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.provenance.artifact_type != ArtifactType.QUALITY_ANNOTATION:
            raise ValueError(
                f"QualityAnnotation provenance must be artifact_type "
                f"{ArtifactType.QUALITY_ANNOTATION}, got {self.provenance.artifact_type}"
            )
        if not self.target_source_record_id:
            raise ValueError("target_source_record_id must be non-empty")
        # Exactly one source_record edge (this target) and at least one scope edge.
        if self.provenance.source_record_ids() != (self.target_source_record_id,):
            raise ValueError(
                "QualityAnnotation provenance must name exactly its target as the one "
                f"source_record edge (target={self.target_source_record_id!r}, "
                f"edges={self.provenance.source_record_ids()})"
            )
        if not self.provenance.input_ids_of(InputType.ANNOTATION):
            raise ValueError(
                "QualityAnnotation provenance must name its DuplicateScope as an "
                "annotation input"
            )
        assign_payload_hash(
            self,
            ArtifactType.QUALITY_ANNOTATION,
            {
                "target_source_record_id": self.target_source_record_id,
                "quality_status": self.quality_status,
                "quality_flags": list(self.quality_flags),
                "evidence": list(self.evidence),
            },
        )


@dataclass(frozen=True, slots=True)
class DuplicateDetectionResult:
    """The full output of one detector run: the scope artifact plus one
    annotation per member, in input order."""

    scope: DuplicateScope
    annotations: tuple[QualityAnnotation, ...]


def is_duplicate_row(annotation: QualityAnnotation) -> bool:
    """The intended consumer read: duplicate-ness lives in ``quality_flags``, never
    in ``quality_status`` (assembly / dedup call this, per M1A.5 review B1)."""
    return QualityFlag.DUPLICATE_ROW in annotation.quality_flags


def detect_duplicate_rows(
    records: Iterable["CanonicalSourceRecord"],
) -> DuplicateDetectionResult:
    """Flag byte-identical rows **within one candidate identity group**.

    ``records`` must be exactly the members of a single resolved-or-candidate
    identity group — there is deliberately no file/corpus scope (M1A.5 review B1),
    because identical bytes routinely span distinct provisions and a wider scope
    would invent duplicate relationships across unrelated law.

    Returns a :class:`DuplicateDetectionResult`: a :class:`DuplicateScope` keyed by
    the complete member set and one :class:`QualityAnnotation` per member (input
    order preserved). A row whose ``raw_text_hash`` collides with at least one
    other member gets a ``duplicate_row`` flag; every other member gets a flagless
    ``unknown`` annotation. Null-text rows are never duplicates (no content to
    address), matching ``raw_text_hash is None``.
    """
    materialized = list(records)
    # Canonical (sorted) member set: the scope is content-addressed by this set, so
    # its stored membership must be order-independent too — reversing the input rows
    # must yield a byte-identical DuplicateScope, not just an id-equal one (M1A.5
    # review P1). Per-member annotation order is preserved separately, below.
    canonical_member_ids = tuple(sorted(rec.source_record_id for rec in materialized))

    scope_prov = DerivedArtifactProvenance.build(
        ArtifactType.DUPLICATE_SCOPE,
        source_record_inputs(canonical_member_ids),  # the COMPLETE member set
        PRODUCER_NAME,
        PRODUCER_VERSION,
    )
    scope = DuplicateScope(
        provenance=scope_prov,
        member_source_record_ids=canonical_member_ids,
        evidence=(
            Evidence(
                "identity_group_scope",
                f"duplicate detection scoped to one identity group of "
                f"{len(canonical_member_ids)} member(s)",
                confidence=1.0,
            ),
        ),
    )

    by_hash: dict[str, list[str]] = defaultdict(list)
    for rec in materialized:
        if rec.raw_text_hash is not None:
            by_hash[rec.raw_text_hash].append(rec.source_record_id)

    annotations: list[QualityAnnotation] = []
    for rec in materialized:
        # Two edges: the scope artifact (so a membership change re-hashes this
        # conclusion) and this record (so two members never share an id).
        provenance = DerivedArtifactProvenance.build(
            ArtifactType.QUALITY_ANNOTATION,
            (
                ArtifactInput(InputType.ANNOTATION, scope.provenance.artifact_id),
                ArtifactInput(InputType.SOURCE_RECORD, rec.source_record_id),
            ),
            PRODUCER_NAME,
            PRODUCER_VERSION,
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
                    f"raw_text_hash shared by {len(siblings)} rows in identity group: "
                    + ", ".join(sorted(siblings)),
                    confidence=1.0,
                ),
            )
            if is_dup
            else ()
        )
        annotations.append(
            QualityAnnotation(
                provenance=provenance,
                target_source_record_id=rec.source_record_id,
                quality_status=QualityStatus.UNKNOWN,
                quality_flags=flags,
                evidence=evidence,
            )
        )

    return DuplicateDetectionResult(scope=scope, annotations=tuple(annotations))
