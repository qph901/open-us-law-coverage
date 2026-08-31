"""Identity as a content-addressed group + per-member annotations (M1A.5, NEXT.md D1).

Identity **groups and characterizes; it never composes.** It may conclude
"R1/R2/R3 appear related, candidate = CFR §X" but must **not** decide "append R2
after R1" — that composition decision belongs to :mod:`.assembly`. Correct
abstention is success; **100% identity coverage is not a metric** (``PROPOSAL.md``
M0.5A / M0.5A.1).

The shape is the ``DuplicateScope`` analogue (NEXT.md D1). An earlier design put a
single ``SourceIdentityAnnotation`` on a multi-member group with **scalar** segment
fields (``segment_fingerprint``, ``segment_ordinal``) — which are unbound on a
multi-member object (*which* member is the fingerprint about?) — and grouped members
through a *mutable* ``source_identity_key`` with no group artifact, reintroducing
the incomplete-recompute-frontier bug ``DuplicateScope`` fixes. Replaced by:

* :class:`SourceIdentityGroup` — content-addressed by the **complete** member set;
* :class:`SourceIdentityMemberAnnotation` — one per member, carrying that member's
  segment fields, naming ``[group, this source_record]`` as inputs.

So changing a member re-hashes the group **and** every affected member annotation.
The 1:1 case is the degenerate single-member group (``single_record`` /
``not_applicable``); the scalar segment fields never again sit unbound on a
multi-member object. Concrete strategies (``usc_act_id_v1`` /
``state_statute_act_id_v1`` / ``cfr_identity_v1`` / ``federal_register_document_v1``)
land with their producers (Phase B); this module fixes the shape and the
segment-order semantics hard-gated by M0.5A.1 (``segment_ordinal`` is
*snapshot-observed physical row order* only, never a reading order).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .provenance import (
    ArtifactType,
    DerivedArtifactProvenance,
    Evidence,
    InputType,
    assign_payload_hash,
)


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
class SourceIdentityGroup:
    """A candidate identity group over one or more ``CanonicalSourceRecord``s.

    Content-addressed by the **complete** member set: its provenance edges are the
    sorted ``source_record`` ids of every member, so the group id is stable under
    reordering but changes the instant a member is added or removed.
    ``member_source_record_ids`` carries no composed text and makes no append
    decision — those belong to :class:`~.assembly.SourceDocumentAssembly`. The
    mutable ``source_identity_key`` lives here (it groups), but no *immutable*
    downstream artifact is keyed by it (the durable-FK rule).
    """

    provenance: DerivedArtifactProvenance
    strategy_name: str
    source_identity_key: str
    member_source_record_ids: tuple[str, ...]
    identity_scope: IdentityScope
    identity_status: IdentityStatus
    confidence: float
    payload_hash: str = ""
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.provenance.artifact_type != ArtifactType.SOURCE_IDENTITY_GROUP:
            raise ValueError(
                f"identity group provenance must be artifact_type "
                f"{ArtifactType.SOURCE_IDENTITY_GROUP}, got "
                f"{self.provenance.artifact_type}"
            )
        if not self.strategy_name:
            raise ValueError("strategy_name must be non-empty")
        if not self.source_identity_key:
            raise ValueError("source_identity_key must be non-empty")
        members = self.member_source_record_ids
        if len(members) == 0:
            raise ValueError("a SourceIdentityGroup must have at least one member")
        if len(set(members)) != len(members):
            raise ValueError(f"duplicate group members are not allowed: {members}")
        # The stored member set must be canonical (sorted) and exactly equal to the
        # provenance source_record edges — otherwise the content address names a
        # different set than the object claims (NEXT.md A.3/A.4).
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
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence!r}")
        assign_payload_hash(
            self,
            ArtifactType.SOURCE_IDENTITY_GROUP,
            {
                "strategy_name": self.strategy_name,
                "source_identity_key": self.source_identity_key,
                "member_source_record_ids": list(members),
                "identity_scope": self.identity_scope,
                "identity_status": self.identity_status,
                "confidence": self.confidence,
                "evidence": list(self.evidence),
            },
        )


@dataclass(frozen=True, slots=True)
class SourceIdentityMemberAnnotation:
    """One member's characterization within a :class:`SourceIdentityGroup`.

    Names two inputs — the group artifact (so a membership change re-hashes this
    conclusion) and its own ``target_source_record_id`` (so two members never share
    an id). The segment fields are **bound to this member** and honor the M0.5A.1
    hard gate: ``segment_ordinal`` is snapshot-observed physical row order only.
    """

    provenance: DerivedArtifactProvenance
    target_source_record_id: str
    segment_fingerprint: str | None = None
    segment_ordinal: int | None = None
    segment_order_method: SegmentOrderMethod = SegmentOrderMethod.UNKNOWN
    segment_order_confidence: SegmentOrderConfidence = (
        SegmentOrderConfidence.NOT_APPLICABLE
    )
    payload_hash: str = ""
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if (
            self.provenance.artifact_type
            != ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION
        ):
            raise ValueError(
                f"member annotation provenance must be artifact_type "
                f"{ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION}, got "
                f"{self.provenance.artifact_type}"
            )
        if not self.target_source_record_id:
            raise ValueError("target_source_record_id must be non-empty")
        # Exactly one source_record edge, and it is this member's target.
        if self.provenance.source_record_ids() != (self.target_source_record_id,):
            raise ValueError(
                "member annotation provenance must name exactly its target as the "
                f"one source_record edge (target={self.target_source_record_id!r}, "
                f"edges={self.provenance.source_record_ids()})"
            )
        # It must anchor to exactly one group — a single ANNOTATION edge (the group
        # artifact_id). "Exactly one", not "at least one" (NEXT.md: inputs are exactly
        # ``[group, target]``): a second annotation edge would let one member claim
        # membership in two groups under one conclusion id.
        if len(self.provenance.input_ids_of(InputType.ANNOTATION)) != 1:
            raise ValueError(
                "member annotation provenance must name exactly one SourceIdentityGroup "
                f"as its annotation input (got "
                f"{self.provenance.input_ids_of(InputType.ANNOTATION)})"
            )
        # ...and nothing else: the inputs are exactly [group, target].
        if len(self.provenance.inputs) != 2:
            raise ValueError(
                "member annotation provenance inputs must be exactly [group, target], "
                f"got {self.provenance.inputs}"
            )
        assign_payload_hash(
            self,
            ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION,
            {
                "target_source_record_id": self.target_source_record_id,
                "segment_fingerprint": self.segment_fingerprint,
                "segment_ordinal": self.segment_ordinal,
                "segment_order_method": self.segment_order_method,
                "segment_order_confidence": self.segment_order_confidence,
                "evidence": list(self.evidence),
            },
        )


@dataclass(frozen=True, slots=True)
class SourceIdentityResult:
    """The full output of one identity-strategy run over a group: the group artifact
    plus **exactly one** member annotation per group member, each linked back to the
    group (member order preserved), mirroring :class:`~.quality.DuplicateDetectionResult`.
    """

    group: SourceIdentityGroup
    members: tuple[SourceIdentityMemberAnnotation, ...]

    def __post_init__(self) -> None:
        group_members = set(self.group.member_source_record_ids)
        targets = [m.target_source_record_id for m in self.members]
        # A bijection: one annotation per group member, no duplicates, no strays.
        if len(targets) != len(group_members) or set(targets) != group_members:
            raise ValueError(
                "SourceIdentityResult must carry exactly one member annotation per "
                f"group member (group={sorted(group_members)}, "
                f"annotation targets={sorted(targets)})"
            )
        # Every annotation must name *this* group as its annotation edge.
        group_id = self.group.provenance.artifact_id
        for m in self.members:
            if m.provenance.input_ids_of(InputType.ANNOTATION) != (group_id,):
                raise ValueError(
                    f"member annotation for {m.target_source_record_id!r} does not "
                    f"link to this group (expected annotation edge {group_id!r})"
                )
