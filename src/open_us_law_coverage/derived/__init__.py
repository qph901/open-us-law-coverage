"""M1A.5 — the shared derived-artifact foundation.

Everything in this subpackage sits on the *interpretation* side of the versioned
boundary (see ``PROPOSAL.md`` "Settled architecture"): it is what our parsers
*believe*, never what the dataset said. The immutable ``CanonicalSourceRecord``
core (M1A) knows nothing about any of it, and rebuilding any layer here has
**zero** effect on ``source_record_id`` / ``raw_text_hash``.

Layer order (locked): ``CanonicalSourceRecord[] -> SourceIdentityAnnotation
(group) -> SourceDocumentAssembly (compose) -> DocumentAnatomy (parse) ->
LegalDocumentView``. This package delivers the first three interfaces plus their
M1A.5 producers:

* :mod:`.provenance` — ``DerivedArtifactProvenance`` as a **multi-input DAG**.
  Every artifact carries one; durable references anchor to ``source_record_id``,
  never to ``source_identity_key``.
* :mod:`.identity` — ``SourceIdentityAnnotation`` (groups/characterizes only,
  **never composes**).
* :mod:`.classification` — ``DocumentClassificationAnnotation`` + the
  near-deterministic first producer.
* :mod:`.quality` — ``QualityAnnotation`` + the ``duplicate_row``-only first
  producer (contamination detector deferred).
* :mod:`.assembly` — ``SourceDocumentAssembly`` + the ``trivial_single_record_v1``
  producer (the 99% one-row case). ``legal_id`` attaches to the assembly.
"""

from __future__ import annotations

from .assembly import (
    AssemblyStatus,
    AssemblyStrategy,
    MemberRole,
    Operation,
    SourceDocumentAssembly,
    assemble_trivial_single_record,
    compute_assembled_text_hash,
)
from .classification import (
    AuthorityRole,
    DocumentClass,
    DocumentClassificationAnnotation,
    classify_source_record,
)
from .identity import (
    IdentityScope,
    IdentityStatus,
    SegmentOrderConfidence,
    SegmentOrderMethod,
    SourceIdentityAnnotation,
)
from .provenance import (
    ArtifactInput,
    ArtifactType,
    DerivedArtifactProvenance,
    Evidence,
    InputType,
    compute_artifact_id,
    source_record_inputs,
)
from .quality import (
    QualityAnnotation,
    QualityFlag,
    QualityStatus,
    detect_duplicate_rows,
)

__all__ = [
    # provenance
    "ArtifactInput",
    "ArtifactType",
    "DerivedArtifactProvenance",
    "Evidence",
    "InputType",
    "compute_artifact_id",
    "source_record_inputs",
    # identity
    "IdentityScope",
    "IdentityStatus",
    "SegmentOrderConfidence",
    "SegmentOrderMethod",
    "SourceIdentityAnnotation",
    # classification
    "AuthorityRole",
    "DocumentClass",
    "DocumentClassificationAnnotation",
    "classify_source_record",
    # quality
    "QualityAnnotation",
    "QualityFlag",
    "QualityStatus",
    "detect_duplicate_rows",
    # assembly
    "AssemblyStatus",
    "AssemblyStrategy",
    "MemberRole",
    "Operation",
    "SourceDocumentAssembly",
    "assemble_trivial_single_record",
    "compute_assembled_text_hash",
]
