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
    ArtifactInput,
    ArtifactType,
    DerivedArtifactProvenance,
    Evidence,
    InputType,
    assign_payload_hash,
    require_enum_member,
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
    payload_hash: str = ""
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        for i, role in enumerate(self.member_roles):
            require_enum_member(role, MemberRole, f"member_roles[{i}]")
        for i, operation in enumerate(self.operations):
            require_enum_member(operation, Operation, f"operations[{i}]")
        require_enum_member(
            self.assembly_strategy, AssemblyStrategy, "assembly_strategy"
        )
        require_enum_member(self.assembly_status, AssemblyStatus, "assembly_status")
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
        # Exact membership (M1A.5 A.4): no duplicate members, and the canonical
        # (sorted, unique) member set must exactly equal the provenance source_record
        # inputs — a set-only check would silently accept a member listed twice.
        # Member *order* is still meaningful (operations are parallel to members), so
        # only the canonicalized comparison is order-independent, not the stored tuple.
        if len(set(self.member_source_record_ids)) != n:
            raise ValueError(
                f"duplicate assembly members are not allowed: "
                f"{self.member_source_record_ids}"
            )
        if tuple(sorted(self.member_source_record_ids)) != self.provenance.source_record_ids():
            raise ValueError(
                "member_source_record_ids must exactly match the provenance "
                f"source_record inputs (members={sorted(self.member_source_record_ids)}, "
                f"provenance={list(self.provenance.source_record_ids())})"
            )
        permitted_inputs = {InputType.SOURCE_RECORD, InputType.ORACLE_EDITION}
        invalid_inputs = [
            edge for edge in self.provenance.inputs if edge.input_type not in permitted_inputs
        ]
        if invalid_inputs:
            raise ValueError(
                "assembly provenance accepts only source_record and oracle_edition "
                f"inputs, got {invalid_inputs}"
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
        assign_payload_hash(
            self,
            ArtifactType.SOURCE_DOCUMENT_ASSEMBLY,
            {
                "member_source_record_ids": list(self.member_source_record_ids),
                "member_roles": list(self.member_roles),
                "operations": list(self.operations),
                "assembly_strategy": self.assembly_strategy,
                "assembly_status": self.assembly_status,
                "assembled_text_hash": self.assembled_text_hash,
                "confidence": self.confidence,
                "evidence": list(self.evidence),
            },
        )


@dataclass(frozen=True, slots=True)
class AssemblyIdentityAssociation:
    """A versioned link from an identity strategy's key (+ ``legal_id``) to an
    immutable assembly artifact — **not** a field on the content-addressed assembly.

    This is where the mutable ``source_identity_key`` lives and where ``legal_id``
    attaches. It may be re-emitted with a new ``strategy_version`` (and a different
    key) when an identity strategy improves, without producing two assembly bodies
    under one ``assembly_artifact_id`` (M1A.5 review B3).

    It is a **first-class derived artifact** like every other (M1A.5 A.2/A.3): it
    carries a :class:`DerivedArtifactProvenance` — one ``assembly`` edge to the body it
    links — and a validated ``payload_hash``, so the collision tripwire covers it too.
    The distinction from the assembly it points at is *where the key lives*: the key
    (and ``legal_id``) ride in **this** artifact's body, never on the content-addressed
    assembly. The key is deliberately **not** a provenance edge (the durable-FK rule);
    it is folded into the derivation ``config_hash`` so two keys pointing at one
    assembly get two distinct ``artifact_id``s instead of colliding.
    """

    provenance: DerivedArtifactProvenance
    source_identity_key: str
    assembly_artifact_id: str
    legal_id: str | None = None
    payload_hash: str = ""
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.provenance.artifact_type != ArtifactType.ASSEMBLY_IDENTITY_ASSOCIATION:
            raise ValueError(
                f"association provenance must be artifact_type "
                f"{ArtifactType.ASSEMBLY_IDENTITY_ASSOCIATION}, got "
                f"{self.provenance.artifact_type}"
            )
        # An association with an empty key or dangling assembly id is a bug — it would
        # anchor ``legal_id`` to nothing (M1A.5 A.3).
        if not self.source_identity_key:
            raise ValueError("source_identity_key must be non-empty")
        if not self.assembly_artifact_id:
            raise ValueError("assembly_artifact_id must be non-empty")
        # The single provenance edge is the assembly this association links, and it is
        # named as an ``assembly`` edge (never a ``source_record`` — the association
        # rests on the composed body, not the physical rows directly).
        if self.provenance.input_ids_of(InputType.ASSEMBLY) != (
            self.assembly_artifact_id,
        ):
            raise ValueError(
                "association provenance must name exactly its assembly as the one "
                f"assembly edge (assembly={self.assembly_artifact_id!r}, edges="
                f"{self.provenance.input_ids_of(InputType.ASSEMBLY)})"
            )
        if len(self.provenance.inputs) != 1:
            raise ValueError(
                "association provenance inputs must be exactly [assembly], got "
                f"{self.provenance.inputs}"
            )
        # The mutable key must NEVER be a provenance edge (durable-FK rule).
        if self.source_identity_key in {e.input_id for e in self.provenance.inputs}:
            raise ValueError("source_identity_key must not be a provenance edge")
        assign_payload_hash(
            self,
            ArtifactType.ASSEMBLY_IDENTITY_ASSOCIATION,
            {
                "source_identity_key": self.source_identity_key,
                "assembly_artifact_id": self.assembly_artifact_id,
                "legal_id": self.legal_id,
                "producer_name": self.provenance.producer_name,
                "producer_version": self.provenance.producer_version,
                "evidence": list(self.evidence),
            },
        )


def assemble_trivial_single_record(
    record: "CanonicalSourceRecord",
) -> SourceDocumentAssembly:
    """The one-row pass-through: keep the single member's ``raw_text`` verbatim.

    Near-free by design, this covers the ~99% of corpora that are one row per
    document. ``assembled_text`` is exactly ``raw_text``, so the assembly never
    invents or drops a byte. A **null** source body is ``NONCOMPOSABLE`` (there is
    nothing returnable to compose); an empty string ``""`` is a valid, complete
    empty provision. The assembly is not keyed by any identity key — associate it
    with one via :func:`associate_assembly_with_identity`.

    The producer version is the module constant ``TRIVIAL_PRODUCER_VERSION`` and is
    **not** caller-overridable (M1A.5 A.5): the version is a property of the code,
    not the call site — a caller that could relabel it could forge a v1 id from v2
    output, or hide a real shape change behind an old version.
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
        TRIVIAL_PRODUCER_VERSION,
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
    and key B may both point at one ``assembly_artifact_id`` without changing it. They
    do get distinct association ``artifact_id``s, because the key (+ ``legal_id``) is
    folded into the derivation ``config_hash`` — so the collision tripwire never fires
    on two legitimately-different associations over one assembly.
    """
    if not strategy_name or not strategy_version:
        raise ValueError("strategy_name and strategy_version must be non-empty")
    assembly_id = assembly.provenance.artifact_id
    # The key + legal_id distinguish two associations over the same assembly; they are
    # the derivation config (never a provenance edge — the durable-FK rule).
    config_hash = hashlib.sha256(
        "\x00".join((source_identity_key, legal_id or "")).encode("utf-8")
    ).hexdigest()
    provenance = DerivedArtifactProvenance.build(
        ArtifactType.ASSEMBLY_IDENTITY_ASSOCIATION,
        (ArtifactInput(InputType.ASSEMBLY, assembly_id),),
        strategy_name,
        strategy_version,
        config_hash=config_hash,
    )
    return AssemblyIdentityAssociation(
        provenance=provenance,
        source_identity_key=source_identity_key,
        assembly_artifact_id=assembly_id,
        legal_id=legal_id,
    )
