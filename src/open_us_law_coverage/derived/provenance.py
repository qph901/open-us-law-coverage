"""``DerivedArtifactProvenance`` — the multi-input provenance DAG (M1A.5).

Every derived artifact carries one of these. The load-bearing properties
(``PROPOSAL.md`` "Data contracts"):

* ``artifact_id = hash(sorted(input_ids), artifact_type, producer_name,
  producer_version, config_hash)`` with ``generated_at`` **excluded** — so the id
  is content-addressed and a byte-identical recompute yields the same id.
* ``inputs[]`` are the **DAG edges**. Because the input set is *sorted* before
  hashing, two artifacts over different member sets never collide, and the DAG
  makes the recompute frontier on a new snapshot **computable** (recompute
  exactly the artifacts whose input set changed).
* Durable references anchor to ``source_record_id`` (an ``input_type ==
  source_record`` edge), **never** to ``source_identity_key`` — which changes
  when an identity strategy improves. The durable-FK test enforces this.

A per-record annotation is simply the single-input case. A build-time oracle
(USLM / eCFR edition) enters as an ``oracle_edition`` input, so downstream hashes
like ``operative_text_hash`` / ``assembled_text_hash`` honor the full-input
reproducibility contract.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# Closed vocabularies. StrEnum (3.12) values compare equal to their str, so
# serialization and hashing stay plain-text and stable.
# ---------------------------------------------------------------------------

class InputType(StrEnum):
    """The kinds of DAG edge an artifact can depend on."""

    SOURCE_RECORD = "source_record"
    ASSEMBLY = "assembly"
    ANNOTATION = "annotation"
    ORACLE_EDITION = "oracle_edition"


class ArtifactType(StrEnum):
    """Every derived-artifact type that carries a ``DerivedArtifactProvenance``."""

    SOURCE_IDENTITY_ANNOTATION = "source_identity_annotation"
    DOCUMENT_CLASSIFICATION_ANNOTATION = "document_classification_annotation"
    QUALITY_ANNOTATION = "quality_annotation"
    SOURCE_DOCUMENT_ASSEMBLY = "source_document_assembly"


# ---------------------------------------------------------------------------
# Evidence — the project's ethos is evidence-first (uncertainty is data, never
# hidden in code), so even the scaffolding carries a structured evidence slot.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Evidence:
    """One auditable reason a producer reached its conclusion.

    ``kind`` is a short machine slug (e.g. ``act_id_prefix``,
    ``byte_identical_text``); ``detail`` is human-readable; ``confidence`` is an
    optional 0..1 contribution.
    """

    kind: str
    detail: str
    confidence: float | None = None


# ---------------------------------------------------------------------------
# DAG edge + id computation.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ArtifactInput:
    """One edge into an artifact: what it was derived from."""

    input_type: InputType
    input_id: str


_UNIT = "\x1f"  # within one edge: separates type from id
_RECORD = "\x1e"  # between edges
_FIELD = "\x00"  # between the top-level fields


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_input(edge: ArtifactInput) -> str:
    return f"{edge.input_type}{_UNIT}{edge.input_id}"


def compute_artifact_id(
    artifact_type: ArtifactType | str,
    inputs: Iterable[ArtifactInput],
    producer_name: str,
    producer_version: str,
    config_hash: str = "",
) -> str:
    """Content-addressed id of a derived artifact.

    Order-independent in ``inputs`` (they are sorted first) and independent of
    ``generated_at`` (audit-only, never hashed). Two producers that emit the same
    conclusion over the same input set from the same config collapse to one id;
    changing *any* input, the producer identity, or the config changes it.
    """
    canon_inputs = _RECORD.join(sorted(_canonical_input(e) for e in inputs))
    payload = _FIELD.join(
        (str(artifact_type), producer_name, producer_version, config_hash, canon_inputs)
    ).encode("utf-8")
    return "art:sha256:" + _sha256_hex(payload)


def source_record_inputs(source_record_ids: Sequence[str]) -> tuple[ArtifactInput, ...]:
    """Convenience: turn ``source_record_id``s into ``source_record`` DAG edges."""
    return tuple(
        ArtifactInput(InputType.SOURCE_RECORD, rid) for rid in source_record_ids
    )


# ---------------------------------------------------------------------------
# The provenance record.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class DerivedArtifactProvenance:
    """Shared provenance for every derived artifact — a multi-input DAG node."""

    artifact_id: str
    artifact_type: ArtifactType
    inputs: tuple[ArtifactInput, ...]
    producer_name: str
    producer_version: str
    config_hash: str = ""
    generated_at: str | None = None  # audit metadata only; NEVER in artifact_id

    @classmethod
    def build(
        cls,
        artifact_type: ArtifactType,
        inputs: Iterable[ArtifactInput],
        producer_name: str,
        producer_version: str,
        *,
        config_hash: str = "",
        generated_at: str | None = None,
    ) -> "DerivedArtifactProvenance":
        """Construct provenance with a computed ``artifact_id``."""
        edges = tuple(inputs)
        return cls(
            artifact_id=compute_artifact_id(
                artifact_type, edges, producer_name, producer_version, config_hash
            ),
            artifact_type=artifact_type,
            inputs=edges,
            producer_name=producer_name,
            producer_version=producer_version,
            config_hash=config_hash,
            generated_at=generated_at,
        )

    def source_record_ids(self) -> tuple[str, ...]:
        """The ``source_record`` edges — the physical rows this artifact rests on."""
        return tuple(
            e.input_id for e in self.inputs if e.input_type == InputType.SOURCE_RECORD
        )

    def input_ids_of(self, input_type: InputType) -> tuple[str, ...]:
        return tuple(e.input_id for e in self.inputs if e.input_type == input_type)
