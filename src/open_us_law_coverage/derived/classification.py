"""``DocumentClassificationAnnotation`` + its near-deterministic first producer (M1A.5).

Even where trivially deterministic (an ``FR_*`` prefix => Federal Register) this
is *our* semantic interpretation of a source field, so it is a regenerable,
versioned annotation — never a slot on the immutable core. ``corpus`` is **not**
sufficient to describe legal role: ``document_class`` / ``authority_role`` are
first-class, and downstream retrieval policy must not assume same-corpus =>
same retrieval semantics.

Retrieval-policy consequence to test now (``PROPOSAL.md`` M0.5A.1): Federal
Register defaults **OFF** for present-law / exact-CFR resolution — its rows are
co-numbered captures, not operative law. See :func:`fr_default_off`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

from .provenance import (
    ArtifactType,
    DerivedArtifactProvenance,
    Evidence,
    source_record_inputs,
)

if TYPE_CHECKING:  # avoid a runtime dep on the immutable-core module
    from open_us_law_coverage.source_record import CanonicalSourceRecord


PRODUCER_NAME = "document_classification_deterministic"
PRODUCER_VERSION = "1"


class DocumentClass(StrEnum):
    CODIFIED_CFR = "codified_cfr"
    FEDERAL_REGISTER = "federal_register"
    STATUTE = "statute"
    REGULATION = "regulation"
    CONSTITUTION = "constitution"
    COURT_RULE = "court_rule"
    GUIDANCE = "guidance"
    UNKNOWN = "unknown"


class AuthorityRole(StrEnum):
    OPERATIVE_PRIMARY_LAW = "operative_primary_law"
    PROMULGATION_RECORD = "promulgation_record"
    EDITORIAL_MATERIAL = "editorial_material"
    GUIDANCE = "guidance"
    UNKNOWN = "unknown"


# act_id namespace prefix (before the first "_") -> (class, role). The first
# producer keys on the M0-observed prefixes; anything else abstains to unknown
# and a later, versioned producer refines it.
_PREFIX_MAP: dict[str, tuple[DocumentClass, AuthorityRole]] = {
    "USC": (DocumentClass.STATUTE, AuthorityRole.OPERATIVE_PRIMARY_LAW),
    "STATE": (DocumentClass.STATUTE, AuthorityRole.OPERATIVE_PRIMARY_LAW),
    "SCONST": (DocumentClass.CONSTITUTION, AuthorityRole.OPERATIVE_PRIMARY_LAW),
    "CFR": (DocumentClass.CODIFIED_CFR, AuthorityRole.OPERATIVE_PRIMARY_LAW),
    "FR": (DocumentClass.FEDERAL_REGISTER, AuthorityRole.PROMULGATION_RECORD),
}


@dataclass(frozen=True, slots=True)
class DocumentClassificationAnnotation:
    provenance: DerivedArtifactProvenance
    document_class: DocumentClass
    authority_role: AuthorityRole
    confidence: float
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)


def act_id_prefix(act_id: str | None) -> str | None:
    """The namespace prefix of an ``act_id`` (``USC_T42_..`` -> ``USC``)."""
    if not act_id:
        return None
    return act_id.split("_", 1)[0]


def classify_act_id(
    act_id: str | None,
) -> tuple[DocumentClass, AuthorityRole, float, Evidence]:
    """Pure classification of one ``act_id`` — the testable core of the producer."""
    prefix = act_id_prefix(act_id)
    mapped = _PREFIX_MAP.get(prefix) if prefix is not None else None
    if mapped is None:
        return (
            DocumentClass.UNKNOWN,
            AuthorityRole.UNKNOWN,
            0.0,
            Evidence(
                "act_id_prefix",
                f"unrecognized act_id namespace prefix {prefix!r}; abstaining",
            ),
        )
    doc_class, role = mapped
    return (
        doc_class,
        role,
        1.0,
        Evidence(
            "act_id_prefix",
            f"prefix {prefix!r} -> {doc_class}/{role}",
            confidence=1.0,
        ),
    )


def classify_source_record(
    record: "CanonicalSourceRecord",
    *,
    producer_version: str = PRODUCER_VERSION,
) -> DocumentClassificationAnnotation:
    """Produce a ``DocumentClassificationAnnotation`` for one source record.

    Provenance anchors to the record's ``source_record_id`` (never to any
    identity key). Duck-typed on ``.source_record_id`` and ``.column('act_id')``,
    so it needs no import of the immutable-core module at runtime.
    """
    act_id = record.column("act_id")
    doc_class, role, confidence, evidence = classify_act_id(act_id)
    provenance = DerivedArtifactProvenance.build(
        ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION,
        source_record_inputs([record.source_record_id]),
        PRODUCER_NAME,
        producer_version,
    )
    return DocumentClassificationAnnotation(
        provenance=provenance,
        document_class=doc_class,
        authority_role=role,
        confidence=confidence,
        evidence=(evidence,),
    )


def fr_default_off(annotation: DocumentClassificationAnnotation) -> bool:
    """Retrieval-policy hook: is this document excluded from present-law /
    exact-CFR resolution by default? True for the Federal Register."""
    return annotation.document_class == DocumentClass.FEDERAL_REGISTER
