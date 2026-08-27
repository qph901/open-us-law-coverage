"""``SourceDocumentAssembly`` + the ``trivial_single_record_v2`` producer (M1A.5).

Assembly is the layer that **composes** the member records of an identity group
into a single document text — the decision identity is forbidden from making
(``PROPOSAL.md`` "Data contracts", layer order). It sits **between identity and
anatomy**; anatomy validates a candidate assembly, it never generates it.

* The plan/assembly split was **cut** (decision A/D): operations, member roles,
  evidence, and status live as fields *on* this one artifact.
* **The assembly is content-addressed by its physical members**, artifact type,
  producer/version, and config — every stored field is a deterministic result of
  those declared inputs. The ``source_identity_key`` is **not** on the artifact
  (M1A.5 review B3): an unhashed identity key on a content-addressed object lets
  two different bodies share one id. The identity-to-assembly link is a separate,
  versioned :class:`AssemblyIdentityAssociation` that may change when an identity
  strategy improves *without* creating two assembly bodies under one id. This is
  the single attach point for ``legal_id`` the layer exists to provide (M0.5A.1
  disproved 1:1 source-to-document): ``legal_id`` rides on that association, not on
  the immutable assembly and not on the row.
* The 99% one-row case uses ``trivial_single_record_v2``: one member, ``KEEP``,
  ``assembled_text = raw_text`` verbatim (``v1`` is deprecated/invalid — see
  ``TRIVIAL_PRODUCER_VERSION``). The real multi-row CFR composer
  (``cfr_source_assembly_v1``) lands in CFR-A2, gated by the eligibility invariant.
* **Eligibility invariant** (M1A.5 review P1): ``assembly_status == complete``
  implies a non-null, returnable ``assembled_text``. A null source body is
  ``NONCOMPOSABLE``, not a complete empty document (``raw_text == ""`` *is* a valid
  complete empty provision).
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
# v2 is the corrected producer (M1A.5 review). It differs from v1 in three ways
# that change the produced object for the *same* input record — so it MUST NOT
# share v1's artifact_id: (1) no ``source_identity_key`` field; (2) an
# assembly-level ``confidence``; (3) a **null** ``raw_text`` now yields
# ``noncomposable`` rather than a bogus ``complete``. v1 is deprecated/invalid and
# must not be produced. No v1 artifacts were ever persisted — M1A.5 was a scaffold,
# so there is nothing to migrate, only a version boundary to make explicit.
TRIVIAL_PRODUCER_VERSION = "2"
TRIVIAL_PRODUCER_VERSION_DEPRECATED_V1 = "1"  # never persisted; do not emit


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
    # v1 is deprecated/invalid (see TRIVIAL_PRODUCER_VERSION); it is retained only
    # so a hypothetical legacy label still parses, and is never emitted.
    TRIVIAL_SINGLE_RECORD_V1 = "trivial_single_record_v1"
    TRIVIAL_SINGLE_RECORD_V2 = "trivial_single_record_v2"
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
    """A composed document over one identity group.

    Content-addressed by its physical members (via ``provenance``); it carries
    **no** ``source_identity_key`` (see module docstring / M1A.5 review B3). The
    ``__post_init__`` invariants make every stored field a coherent function of the
    inputs: the parallel member tuples share a length, ``complete`` implies a
    non-null ``assembled_text``, the text hash matches the text, and ``confidence``
    is a probability.
    """

    provenance: DerivedArtifactProvenance
    member_source_record_ids: tuple[str, ...]
    member_roles: tuple[MemberRole, ...]
    operations: tuple[Operation, ...]
    assembly_strategy: AssemblyStrategy
    assembly_status: AssemblyStatus
    assembled_text: str | None
    assembled_text_hash: str | None
    confidence: float = 1.0
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        n = len(self.member_source_record_ids)
        if not (len(self.member_roles) == len(self.operations) == n) or n == 0:
            raise ValueError(
                "member_source_record_ids / member_roles / operations must be "
                f"parallel and non-empty (got {n}, {len(self.member_roles)}, "
                f"{len(self.operations)})"
            )
        # The provenance must actually be an assembly node, and its physical members
        # must be exactly this assembly's members (M1A.5 review P2) — otherwise the
        # content address names a different member set than the object claims.
        if self.provenance.artifact_type != ArtifactType.SOURCE_DOCUMENT_ASSEMBLY:
            raise ValueError(
                f"assembly provenance must be artifact_type "
                f"{ArtifactType.SOURCE_DOCUMENT_ASSEMBLY}, got "
                f"{self.provenance.artifact_type}"
            )
        if set(self.provenance.source_record_ids()) != set(self.member_source_record_ids):
            raise ValueError(
                "member_source_record_ids must match the provenance source_record "
                f"inputs (members={sorted(set(self.member_source_record_ids))}, "
                f"provenance={sorted(set(self.provenance.source_record_ids()))})"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence!r}")
        if self.assembled_text_hash != compute_assembled_text_hash(self.assembled_text):
            raise ValueError("assembled_text_hash is inconsistent with assembled_text")
        # Full status/text matrix (M1A.5 review P2), not just complete=>non-null:
        # complete/partial are returnable (non-null text); noncomposable/ambiguous
        # have nothing to return (null text). The hash follows the text, above.
        _text_required = {AssemblyStatus.COMPLETE, AssemblyStatus.PARTIAL}
        _text_forbidden = {AssemblyStatus.NONCOMPOSABLE, AssemblyStatus.AMBIGUOUS}
        if self.assembly_status in _text_required and self.assembled_text is None:
            raise ValueError(
                f"assembly_status {self.assembly_status} requires a non-null, "
                f"returnable assembled_text"
            )
        if self.assembly_status in _text_forbidden and self.assembled_text is not None:
            raise ValueError(
                f"assembly_status {self.assembly_status} requires a null "
                f"assembled_text (nothing composable to return)"
            )


@dataclass(frozen=True, slots=True)
class AssemblyIdentityAssociation:
    """A versioned, explicit link from an identity strategy's key to an immutable
    assembly artifact — **not** a field on the content-addressed assembly.

    This is where the mutable ``source_identity_key`` lives and where ``legal_id``
    attaches. It may be re-emitted with a new ``strategy_version`` (and a different
    key) when an identity strategy improves, without producing two assembly bodies
    under one ``assembly_artifact_id`` (M1A.5 review B3).
    """

    source_identity_key: str
    assembly_artifact_id: str
    strategy_name: str
    strategy_version: str
    legal_id: str | None = None
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)


def assemble_trivial_single_record(
    record: "CanonicalSourceRecord",
    *,
    producer_version: str = TRIVIAL_PRODUCER_VERSION,
) -> SourceDocumentAssembly:
    """The one-row pass-through: keep the single member's ``raw_text`` verbatim.

    Near-free by design, this covers the ~99% of corpora that are one row per
    document. ``assembled_text`` is exactly ``raw_text``, so the assembly never
    invents or drops a byte. A **null** source body is ``NONCOMPOSABLE`` (there is
    nothing returnable to compose); an empty string ``""`` is a valid, complete
    empty provision. The assembly is not keyed by any identity key — associate it
    with one via :func:`associate_assembly_with_identity`.
    """
    if record.raw_text is None:
        assembled_text = None
        status = AssemblyStatus.NONCOMPOSABLE
        evidence = (
            Evidence(
                "null_source_body",
                "single member has a null text body; nothing to compose",
                confidence=1.0,
            ),
        )
    else:
        assembled_text = record.raw_text
        status = AssemblyStatus.COMPLETE
        evidence = (
            Evidence(
                "single_record_group",
                "identity group has exactly one member; kept verbatim",
                confidence=1.0,
            ),
        )

    provenance = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY,
        source_record_inputs([record.source_record_id]),
        TRIVIAL_PRODUCER_NAME,
        producer_version,
    )
    return SourceDocumentAssembly(
        provenance=provenance,
        member_source_record_ids=(record.source_record_id,),
        member_roles=(MemberRole.PRIMARY,),
        operations=(Operation.KEEP,),
        assembly_strategy=AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V2,
        assembly_status=status,
        assembled_text=assembled_text,
        assembled_text_hash=compute_assembled_text_hash(assembled_text),
        confidence=1.0,
        evidence=evidence,
    )


def associate_assembly_with_identity(
    source_identity_key: str,
    assembly: SourceDocumentAssembly,
    *,
    strategy_name: str,
    strategy_version: str,
    legal_id: str | None = None,
) -> AssemblyIdentityAssociation:
    """Link an identity key (and optionally a ``legal_id``) to an assembly artifact.

    Kept out of the content-addressed assembly on purpose (M1A.5 review B3): key A
    and key B may both point at one ``assembly_artifact_id`` without changing it.
    """
    return AssemblyIdentityAssociation(
        source_identity_key=source_identity_key,
        assembly_artifact_id=assembly.provenance.artifact_id,
        strategy_name=strategy_name,
        strategy_version=strategy_version,
        legal_id=legal_id,
    )
