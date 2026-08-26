"""``SourceDocumentAssembly`` + the ``trivial_single_record_v1`` producer (M1A.5).

Assembly is the layer that **composes** the member records of a
``source_identity_key`` group into a single document text — the decision identity
is forbidden from making (``PROPOSAL.md`` "Data contracts", layer order). It sits
**between identity and anatomy**; anatomy validates a candidate assembly, it
never generates it.

* The plan/assembly split was **cut** (decision A/D): operations, member roles,
  evidence, and status live as fields *on* this one artifact.
* **``legal_id`` attaches to the assembly, not the row** — this is the single
  attach point the layer exists to provide (M0.5A.1 disproved 1:1
  source-to-document).
* The 99% one-row case uses ``trivial_single_record_v1``: one member, ``KEEP``,
  ``assembly_status = complete``, ``assembled_text = raw_text``. The real
  multi-row CFR composer (``cfr_source_assembly_v1``) lands in CFR-A2, gated by
  the eligibility invariant.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from .provenance import (
    ArtifactType,
    DerivedArtifactProvenance,
    Evidence,
    source_record_inputs,
)

if TYPE_CHECKING:
    from open_us_law_coverage.source_record import CanonicalSourceRecord


TRIVIAL_PRODUCER_NAME = "source_assembly_trivial_single_record"
TRIVIAL_PRODUCER_VERSION = "1"


class MemberRole(StrEnum):
    PRIMARY = "primary"
    CONTINUATION = "continuation"
    DUPLICATE = "duplicate"
    ALTERNATIVE = "alternative"
    AMBIGUOUS = "ambiguous"


class Operation(StrEnum):
    KEEP = "KEEP"
    APPEND = "APPEND"
    IGNORE_DUPLICATE = "IGNORE_DUPLICATE"
    KEEP_SEPARATE = "KEEP_SEPARATE"
    ABSTAIN = "ABSTAIN"


class AssemblyStrategy(StrEnum):
    TRIVIAL_SINGLE_RECORD_V1 = "trivial_single_record_v1"
    CFR_SOURCE_ASSEMBLY_V1 = "cfr_source_assembly_v1"


class AssemblyStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    NONCOMPOSABLE = "noncomposable"


def compute_assembled_text_hash(assembled_text: str | None) -> str | None:
    """Content address of the composed text — the cross-snapshot change signal for
    multi-row sections. ``None`` when there is nothing composed."""
    if assembled_text is None:
        return None
    return "sha256:" + hashlib.sha256(assembled_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SourceDocumentAssembly:
    """A composed document over one identity group. ``legal_id`` attaches here."""

    provenance: DerivedArtifactProvenance
    source_identity_key: str
    member_source_record_ids: tuple[str, ...]
    member_roles: tuple[MemberRole, ...]
    operations: tuple[Operation, ...]
    assembly_strategy: AssemblyStrategy
    assembly_status: AssemblyStatus
    assembled_text: str | None
    assembled_text_hash: str | None
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)


def assemble_trivial_single_record(
    record: "CanonicalSourceRecord",
    source_identity_key: str,
    *,
    producer_version: str = TRIVIAL_PRODUCER_VERSION,
) -> SourceDocumentAssembly:
    """The one-row pass-through: keep the single member's ``raw_text`` verbatim.

    Near-free by design, this covers the ~99% of corpora that are one row per
    document. ``assembled_text`` is exactly ``raw_text`` (null stays null), so the
    assembly never invents or drops a byte.
    """
    provenance = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY,
        source_record_inputs([record.source_record_id]),
        TRIVIAL_PRODUCER_NAME,
        producer_version,
    )
    return SourceDocumentAssembly(
        provenance=provenance,
        source_identity_key=source_identity_key,
        member_source_record_ids=(record.source_record_id,),
        member_roles=(MemberRole.PRIMARY,),
        operations=(Operation.KEEP,),
        assembly_strategy=AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V1,
        assembly_status=AssemblyStatus.COMPLETE,
        assembled_text=record.raw_text,
        assembled_text_hash=compute_assembled_text_hash(record.raw_text),
        evidence=(
            Evidence(
                "single_record_group",
                "identity group has exactly one member; kept verbatim",
                confidence=1.0,
            ),
        ),
    )
