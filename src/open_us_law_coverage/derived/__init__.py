"""M1A.5 — the shared derived-artifact foundation.

Everything in this subpackage sits on the *interpretation* side of the versioned
boundary (see ``PROPOSAL.md`` "Settled architecture"): it is what our parsers
*believe*, never what the dataset said. The immutable ``CanonicalSourceRecord``
core (M1A) knows nothing about any of it, and rebuilding any layer here has
**zero** effect on ``source_record_id`` / ``raw_text_hash``.

Layer order (locked): ``CanonicalSourceRecord[] -> SourceIdentityGroup (+ member
annotations) -> SourceDocumentAssembly (compose) -> DocumentAnatomy (parse) ->
LegalDocumentView``. This package delivers the first three interfaces plus their
M1A.5 producers:

* :mod:`.provenance` — ``DerivedArtifactProvenance`` as a **multi-input DAG** plus
  the ``payload_hash`` semantic content address and the equal-id/unequal-payload
  tripwire (NEXT.md D2). Every artifact carries both; durable references anchor to
  ``source_record_id``, never to ``source_identity_key``.
* :mod:`.identity` — ``SourceIdentityGroup`` + ``SourceIdentityMemberAnnotation``
  (the ``DuplicateScope`` analogue; groups/characterizes only, **never composes**).
* :mod:`.classification` — ``DocumentClassificationAnnotation`` + the
  near-deterministic first producer.
* :mod:`.quality` — ``QualityAnnotation`` + the ``duplicate_row``-only first
  producer, scoped to one identity group (contamination detector deferred). Each
  conclusion names a content-addressed ``DuplicateScope`` so its recompute frontier
  is complete.
* :mod:`.assembly` — ``SourceDocumentAssembly`` + the ``trivial_single_record_v2``
  producer (the 99% one-row case; v1 deprecated/invalid). The assembly is content-addressed by its
  physical members; the mutable identity key / ``legal_id`` live on a separate
  versioned ``AssemblyIdentityAssociation``.
"""

from __future__ import annotations

from .assembly import (
    AssemblyIdentityAssociation,
    AssemblyStatus,
    AssemblyStrategy,
    MemberRole,
    Operation,
    SourceDocumentAssembly,
    assemble_trivial_single_record,
    associate_assembly_with_identity,
    compute_assembled_text_hash,
)
from .classification import (
    AuthorityRole,
    DocumentClass,
    DocumentClassificationAnnotation,
    classify,
    classify_source_record,
)
from .identity import (
    IdentityScope,
    IdentityStatus,
    SegmentOrderConfidence,
    SegmentOrderMethod,
    SourceIdentityGroup,
    SourceIdentityMemberAnnotation,
    SourceIdentityResult,
)
from .provenance import (
    ArtifactInput,
    ArtifactType,
    DerivedArtifactProvenance,
    Evidence,
    InputType,
    PayloadCollisionError,
    assign_payload_hash,
    canonicalize_inputs,
    check_payload_collisions,
    compute_artifact_id,
    compute_payload_hash,
    source_record_inputs,
)
from .quality import (
    DuplicateDetectionResult,
    DuplicateScope,
    QualityAnnotation,
    QualityFlag,
    QualityStatus,
    detect_duplicate_rows,
    is_duplicate_row,
)

__all__ = [
    # provenance
    "ArtifactInput",
    "ArtifactType",
    "DerivedArtifactProvenance",
    "Evidence",
    "InputType",
    "PayloadCollisionError",
    "assign_payload_hash",
    "canonicalize_inputs",
    "check_payload_collisions",
    "compute_artifact_id",
    "compute_payload_hash",
    "source_record_inputs",
    # identity
    "IdentityScope",
    "IdentityStatus",
    "SegmentOrderConfidence",
    "SegmentOrderMethod",
    "SourceIdentityGroup",
    "SourceIdentityMemberAnnotation",
    "SourceIdentityResult",
    # classification
    "AuthorityRole",
    "DocumentClass",
    "DocumentClassificationAnnotation",
    "classify",
    "classify_source_record",
    # quality
    "DuplicateDetectionResult",
    "DuplicateScope",
    "QualityAnnotation",
    "QualityFlag",
    "QualityStatus",
    "detect_duplicate_rows",
    "is_duplicate_row",
    # assembly
    "AssemblyIdentityAssociation",
    "AssemblyStatus",
    "AssemblyStrategy",
    "MemberRole",
    "Operation",
    "SourceDocumentAssembly",
    "assemble_trivial_single_record",
    "associate_assembly_with_identity",
    "compute_assembled_text_hash",
]
