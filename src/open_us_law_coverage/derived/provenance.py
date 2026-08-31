"""``DerivedArtifactProvenance`` — the multi-input provenance DAG (M1A.5).

Every derived artifact carries one of these. The load-bearing properties
(``PROPOSAL.md`` "Data contracts"):

* ``artifact_id = hash(sorted(input_ids), artifact_type, producer_name,
  producer_version, config_hash)`` with ``generated_at`` **excluded**. This is a
  *derivation* address, not the semantic body: it is a pure function of the declared
  inputs + producer identity + config, so it is pre-computable before the body
  exists (that is what the recompute frontier relies on). The semantic body is
  addressed separately by ``payload_hash`` (M1A.5 closure D2) — equal ``artifact_id`` means
  equal derivation, **not** necessarily an equal conclusion body; the
  :func:`check_payload_collisions` tripwire is what rejects a body that drifted under
  a stale id.
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
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Iterable, Sequence, TypeVar

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

    # Identity is a content-addressed group + per-member annotations (M1A.5 D1,
    # the ``DuplicateScope`` analogue): the group is keyed by the COMPLETE member
    # set, each member annotation names the group and its own record. The old flat
    # ``source_identity_annotation`` — a lone scalar segment unbound on a
    # multi-member object — is withdrawn.
    SOURCE_IDENTITY_GROUP = "source_identity_group"
    SOURCE_IDENTITY_MEMBER_ANNOTATION = "source_identity_member_annotation"
    DOCUMENT_CLASSIFICATION_ANNOTATION = "document_classification_annotation"
    QUALITY_ANNOTATION = "quality_annotation"
    # The detector-run/scope artifact a cross-record quality conclusion names as an
    # input — content-addressed by the *complete* identity-group member set, so any
    # change to membership changes it and the provenance of every conclusion it
    # scopes (M1A.5 review B1).
    DUPLICATE_SCOPE = "duplicate_scope"
    SOURCE_DOCUMENT_ASSEMBLY = "source_document_assembly"
    # The versioned, mutable link from an identity strategy's key (+ ``legal_id``) to
    # an immutable assembly artifact (M1A.5 A.2/A.3). It is a derived artifact like
    # any other — it carries provenance (an ``assembly`` edge to the body it links)
    # and a ``payload_hash`` — but it deliberately does NOT put the mutable key on the
    # content-addressed assembly: the key rides in this artifact's own body instead.
    ASSEMBLY_IDENTITY_ASSOCIATION = "assembly_identity_association"


_EnumT = TypeVar("_EnumT", bound=StrEnum)


def require_enum_member(
    value: object, enum_type: type[_EnumT], field_name: str
) -> _EnumT:
    """Reject values outside a derived model's closed vocabulary.

    Dataclass annotations are not runtime checks.  Requiring the actual ``StrEnum``
    member (rather than accepting any string that happens to serialize) keeps direct
    construction subject to the same contract as producer construction.
    """
    if not isinstance(value, enum_type):
        allowed = ", ".join(repr(member.value) for member in enum_type)
        raise ValueError(
            f"{field_name} must be a {enum_type.__name__} member "
            f"({allowed}), got {value!r}"
        )
    return value


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

    def __post_init__(self) -> None:
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"Evidence.confidence must be in [0, 1] or None, got {self.confidence!r}"
            )
        if not self.kind:
            raise ValueError("Evidence.kind must be non-empty")


# ---------------------------------------------------------------------------
# payload_hash — the SEMANTIC content address (M1A.5 D2).
#
# ``artifact_id`` is a *derivation* address: hash(inputs, type, producer, version,
# config), pre-computable before the body exists — that is what the recompute
# frontier relies on, so the semantic body must NOT be folded into it. But the
# derivation->body guarantee is only as strong as release discipline: a
# deterministic producer whose code changes without a version bump (or an
# output-affecting knob not folded into ``config_hash``) silently emits a new body
# under the old id. So every derived artifact ALSO carries a ``payload_hash``: the
# canonical hash of its semantic conclusion fields (audit-only metadata excluded),
# validated against the body in ``__post_init__``.
#
# This mirrors the M1A house rule that keeps ``source_record_id`` (physical) apart
# from ``raw_text_hash`` (content). The corrected guarantee: equal ``artifact_id``
# => equal (inputs, producer, version, config); equal ``payload_hash`` => equal
# canonical semantic payload; a well-governed store never holds two payloads under
# one ``artifact_id`` (the tripwire in :func:`check_payload_collisions`).
# ---------------------------------------------------------------------------

def _canonical(obj: Any) -> Any:
    """Recursively reduce a payload to JSON-canonical primitives.

    ``StrEnum`` members are ``str`` subclasses, so they serialize as their value.
    ``Evidence`` reduces to an ordered mapping; tuples become lists (JSON has no
    tuple). Anything else is a programming error — better to raise than to hash an
    opaque ``repr`` that could drift.
    """
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):  # includes StrEnum members
        return str(obj)
    if isinstance(obj, Evidence):
        return {"kind": obj.kind, "detail": obj.detail, "confidence": obj.confidence}
    if isinstance(obj, (list, tuple)):
        return [_canonical(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): _canonical(v) for k, v in obj.items()}
    raise TypeError(f"payload field is not canonically serializable: {obj!r}")


def compute_payload_hash(artifact_type: ArtifactType | str, payload: Any) -> str:
    """Canonical hash of a derived artifact's semantic body.

    ``payload`` is the conclusion fields only — ``generated_at`` and any audit-only
    field are excluded by the caller. The ``artifact_type`` is folded in so two
    different artifact kinds with a coincidentally-identical body never collide.
    Serialization is order-stable (``sort_keys``) and tuple/enum-agnostic.
    """
    blob = json.dumps(
        {"t": str(artifact_type), "p": _canonical(payload)},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return "pay:sha256:" + _sha256_hex(blob.encode("utf-8"))


class PayloadCollisionError(ValueError):
    """Two artifacts share an ``artifact_id`` but disagree on ``payload_hash`` — the
    "unbumped producer change" surfaced as an error instead of a silent overwrite."""


def assign_payload_hash(
    instance: Any, artifact_type: ArtifactType | str, payload: Any
) -> None:
    """Compute, validate, and set ``instance.payload_hash`` from its semantic body.

    Mirrors the M1A ``source_record_id`` pattern so direct construction is as safe
    as the producer path: an empty stored value is filled in; a non-empty value that
    disagrees with the recomputed hash is rejected (a caller that hand-set a stale or
    wrong payload hash). Frozen-dataclass friendly (writes via ``object.__setattr__``).
    """
    expected = compute_payload_hash(artifact_type, payload)
    stored = instance.payload_hash
    if stored and stored != expected:
        raise ValueError(
            f"payload_hash {stored!r} is inconsistent with the artifact body "
            f"(recomputed {expected!r})"
        )
    object.__setattr__(instance, "payload_hash", expected)


# ---------------------------------------------------------------------------
# DAG edge + id computation.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ArtifactInput:
    """One edge into an artifact: what it was derived from."""

    input_type: InputType
    input_id: str

    def __post_init__(self) -> None:
        require_enum_member(self.input_type, InputType, "ArtifactInput.input_type")
        if not isinstance(self.input_id, str) or not self.input_id.strip():
            raise ValueError("ArtifactInput.input_id must be a non-empty string")


_UNIT = "\x1f"  # within one edge: separates type from id
_RECORD = "\x1e"  # between edges
_FIELD = "\x00"  # between the top-level fields


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_input(edge: ArtifactInput) -> str:
    return f"{edge.input_type}{_UNIT}{edge.input_id}"


def canonicalize_inputs(inputs: Iterable[ArtifactInput]) -> tuple[ArtifactInput, ...]:
    """The one canonical stored order for a content-addressed input set.

    Input order is **not** semantically load-bearing (the id sorts before hashing),
    so the *stored* edges are sorted by the same key. This makes equal ``artifact_id``
    imply an equal serialized *provenance* tuple — two provenance nodes built from the
    same set in different orders are byte-identical (M1A.5 review P1). Note the scope:
    this is a statement about the ``DerivedArtifactProvenance`` node, **not** the
    derived artifact carrying it — equal ``artifact_id`` does not by itself imply an
    equal conclusion body (that is what ``payload_hash`` addresses; D2). Callers that
    need input-order correspondence keep it separately (e.g. the per-member annotation
    list produced alongside a scope artifact).
    """
    return tuple(sorted(inputs, key=_canonical_input))


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

    def __post_init__(self) -> None:
        """Enforce the content-addressing contract even for direct construction.

        A directly-built provenance whose stored ``artifact_id`` does not match a
        recomputation over its declared inputs is a corrupt DAG node — reject it
        rather than let it name a body it does not address (M1A.5 review P6). Input
        order is *not* load-bearing (``compute_artifact_id`` sorts), but duplicate
        edges are rejected: they would silently double-count a dependency.
        """
        require_enum_member(
            self.artifact_type,
            ArtifactType,
            "DerivedArtifactProvenance.artifact_type",
        )
        if not self.producer_name or not self.producer_version:
            raise ValueError("producer_name and producer_version must be non-empty")
        for edge in self.inputs:
            if not edge.input_id:
                raise ValueError("every ArtifactInput.input_id must be non-empty")
        if len(set(self.inputs)) != len(self.inputs):
            raise ValueError(f"duplicate provenance edges are not allowed: {self.inputs}")
        # Canonicalize stored input order so equal ids <=> equal serialized objects.
        object.__setattr__(self, "inputs", canonicalize_inputs(self.inputs))
        expected = compute_artifact_id(
            self.artifact_type,
            self.inputs,
            self.producer_name,
            self.producer_version,
            self.config_hash,
        )
        if self.artifact_id != expected:
            raise ValueError(
                f"artifact_id {self.artifact_id!r} is inconsistent with its inputs "
                f"(recomputed {expected!r})"
            )

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


def check_payload_collisions(artifacts: Iterable[Any]) -> None:
    """The equal-id / unequal-payload tripwire (M1A.5 D2).

    Any store or test that ingests derived artifacts should run them through this:
    if two artifacts present the same ``provenance.artifact_id`` but different
    ``payload_hash``, a producer changed its output without bumping its version (or
    an output-affecting knob escaped ``config_hash``). That is precisely the silent
    overwrite the derivation/semantic split exists to catch — so raise instead.
    Duck-typed on ``.provenance.artifact_id`` / ``.payload_hash`` (every derived
    artifact has both), so ``derived/`` keeps no import of the immutable core.
    """
    seen: dict[str, str] = {}
    for art in artifacts:
        artifact_id = art.provenance.artifact_id
        payload_hash = art.payload_hash
        prior = seen.get(artifact_id)
        if prior is not None and prior != payload_hash:
            raise PayloadCollisionError(
                f"artifact_id {artifact_id!r} maps to two payloads "
                f"({prior!r} != {payload_hash!r}): an unbumped producer change"
            )
        seen[artifact_id] = payload_hash
