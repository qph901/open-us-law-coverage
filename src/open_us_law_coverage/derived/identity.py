"""``SourceIdentityAnnotation`` — groups/characterizes only, never composes (M1A.5).

Identity may conclude "R1/R2/R3 appear related, candidate = CFR §X" but must
**not** decide "append R2 after R1" — that composition decision belongs to
:mod:`.assembly`. Correct abstention is success; **100% identity coverage is not
a metric** (``PROPOSAL.md`` M0.5A / M0.5A.1).

Identity is emitted by a corpus-specific, versioned ``SourceIdentityStrategy``
(never a hardcoded universal key). The concrete strategies — ``usc_act_id_v1``,
``state_statute_act_id_v1``, ``cfr_identity_v1``, ``federal_register_document_v1``
— land with their producers; this module fixes the artifact shape and the
segment-order semantics hard-gated by M0.5A.1 (``segment_ordinal`` is
*snapshot-observed physical row order* only, never a reading order).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .provenance import DerivedArtifactProvenance, Evidence


class IdentityScope(StrEnum):
    RECORD = "record"
    PROVISION = "provision"
    DOCUMENT = "document"
    SEGMENT = "segment"
    NUMBERING_BUCKET = "numbering_bucket"
    UNKNOWN = "unknown"


class IdentityStatus(StrEnum):
    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    PROVISIONAL = "provisional"
    UNSUPPORTED = "unsupported"


class SegmentOrderMethod(StrEnum):
    """How ``segment_ordinal`` was derived. M0.5A.1 froze physical-row-order as
    the only defensible method for the colliding regulations corpora."""

    PHYSICAL_ROW_ORDER = "physical_row_order"
    SINGLE_RECORD = "single_record"
    UNKNOWN = "unknown"


class SegmentOrderConfidence(StrEnum):
    """M0.5A.1: no *source-defined* ordinal exists for FR/CFR collision groups —
    order is at best snapshot-observed, and FR full-text concatenation is invalid."""

    SNAPSHOT_OBSERVED = "snapshot_observed"
    SOURCE_DEFINED = "source_defined"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class SourceIdentityAnnotation:
    """A candidate identity group over one or more ``CanonicalSourceRecord``s.

    ``member_source_record_ids`` is the candidate group (may be a single record).
    It carries **no** composed text and makes **no** append decision — those are
    :class:`~open_us_law_coverage.derived.assembly.SourceDocumentAssembly`.
    """

    provenance: DerivedArtifactProvenance
    strategy_name: str
    source_identity_key: str
    member_source_record_ids: tuple[str, ...]
    identity_scope: IdentityScope
    identity_status: IdentityStatus
    confidence: float
    # segment fields — snapshot-observed order only (M0.5A.1 hard gate).
    segment_fingerprint: str | None = None
    segment_ordinal: int | None = None
    segment_order_method: SegmentOrderMethod = SegmentOrderMethod.UNKNOWN
    segment_order_confidence: SegmentOrderConfidence = (
        SegmentOrderConfidence.NOT_APPLICABLE
    )
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)
