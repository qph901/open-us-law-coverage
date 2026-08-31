"""``DocumentClassificationAnnotation`` + its near-deterministic first producer (M1A.5).

Even where trivially deterministic (an ``FR_*`` prefix => Federal Register) this
is *our* semantic interpretation of source fields, so it is a regenerable,
versioned annotation — never a slot on the immutable core. ``corpus`` is **not**
sufficient to describe legal role: ``document_class`` / ``authority_role`` are
first-class, and downstream retrieval policy must not assume same-corpus =>
same retrieval semantics.

**Broad class comes from the 100%-populated ``document_type`` column, not the
``act_id`` prefix** (M1A.5 review B2). The ``STATE_*`` namespace collapses
**1,942,637** statute rows with **289,797** *regulation* rows (full v2026.08
snapshot); a prefix-only classifier labels every one of them ``statute`` at
confidence 1.0 and can never reach ``regulation`` / ``court_rule`` / ``guidance``. ``document_type`` distinguishes them (it carries
``statute`` / ``regulation`` / ``constitution`` / ``court_rule`` / ``guidance`` and
a family of sub-regulatory guidance types). The ``act_id`` prefix is then used only
to **refine** a regulation into codified CFR vs. Federal Register, and — for the
few operative namespaces with a fixed expectation — to **detect contradictions**,
in which case the producer abstains rather than guess.

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
    assign_payload_hash,
    require_enum_member,
    source_record_inputs,
)

if TYPE_CHECKING:  # avoid a runtime dep on the immutable-core module
    from open_us_law_coverage.source_record import CanonicalSourceRecord


PRODUCER_NAME = "document_classification_deterministic"
PRODUCER_VERSION = "2"  # v2: document_type-based broad class (v1 was prefix-only)


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


# ``document_type`` value -> (broad class, authority role). This is the load-bearing
# signal (100% populated, M0). Regulations are refined by prefix below; the
# sub-regulatory guidance family (rulings, IRS notices, FAQs, memoranda, …) all map
# to GUIDANCE. Document types with no home in the closed vocabulary
# (``executive_order`` / ``proclamation`` / ``presidential_document`` / ``treaty``)
# deliberately fall through to an explicit abstention rather than a wrong label.
_DOCUMENT_TYPE_CLASS: dict[str, tuple[DocumentClass, AuthorityRole]] = {
    "statute": (DocumentClass.STATUTE, AuthorityRole.OPERATIVE_PRIMARY_LAW),
    "regulation": (DocumentClass.REGULATION, AuthorityRole.OPERATIVE_PRIMARY_LAW),
    "constitution": (DocumentClass.CONSTITUTION, AuthorityRole.OPERATIVE_PRIMARY_LAW),
    "court_rule": (DocumentClass.COURT_RULE, AuthorityRole.OPERATIVE_PRIMARY_LAW),
    "guidance": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "guideline": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "administrative_guidance": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "ruling": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "faq": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "memorandum": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "enforcement_action": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "irs_notice": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "irs_rev_proc": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "irs_rev_rul": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    "irs_announcement": (DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
}

# The few ``act_id`` prefixes with a *fixed* broad-class expectation. Compared
# against the ``document_type``-derived broad class to catch contradictions.
# ``STATE`` is intentionally absent: it is genuinely ambiguous (statute OR
# regulation), so it never contradicts and never disambiguates on its own.
_PREFIX_EXPECTED_CLASS: dict[str, DocumentClass] = {
    "USC": DocumentClass.STATUTE,
    "CFR": DocumentClass.REGULATION,
    "FR": DocumentClass.REGULATION,
    "SCONST": DocumentClass.CONSTITUTION,
    "CONST": DocumentClass.CONSTITUTION,
    "SREGS": DocumentClass.REGULATION,
    "SRULES": DocumentClass.COURT_RULE,
    "FRULES": DocumentClass.COURT_RULE,
}


@dataclass(frozen=True, slots=True)
class DocumentClassificationAnnotation:
    provenance: DerivedArtifactProvenance
    document_class: DocumentClass
    authority_role: AuthorityRole
    confidence: float
    payload_hash: str = ""
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        require_enum_member(self.document_class, DocumentClass, "document_class")
        require_enum_member(self.authority_role, AuthorityRole, "authority_role")
        if (
            self.provenance.artifact_type
            != ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION
        ):
            raise ValueError(
                f"classification provenance must be artifact_type "
                f"{ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION}, got "
                f"{self.provenance.artifact_type}"
            )
        # A per-record annotation rests on exactly one physical row.
        if len(self.provenance.source_record_ids()) != 1:
            raise ValueError(
                "classification provenance must name exactly one source_record input, "
                f"got {self.provenance.source_record_ids()}"
            )
        if len(self.provenance.inputs) != 1:
            raise ValueError(
                "classification provenance inputs must be exactly one "
                f"source_record edge, got {self.provenance.inputs}"
            )
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0, 1], got {self.confidence!r}")
        assign_payload_hash(
            self,
            ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION,
            {
                "document_class": self.document_class,
                "authority_role": self.authority_role,
                "confidence": self.confidence,
                "evidence": list(self.evidence),
            },
        )


def act_id_prefix(act_id: str | None) -> str | None:
    """The namespace prefix of an ``act_id`` (``USC_T42_..`` -> ``USC``)."""
    if not act_id:
        return None
    return act_id.split("_", 1)[0]


def classify(
    document_type: str | None,
    act_id: str | None,
) -> tuple[DocumentClass, AuthorityRole, float, tuple[Evidence, ...]]:
    """Pure classification from ``document_type`` + ``act_id`` — the testable core.

    ``document_type`` sets the broad class; the ``act_id`` prefix refines a
    regulation (CFR vs. FR) and, for the operative namespaces with a fixed
    expectation, gates a contradiction check. On an unmapped ``document_type`` or a
    prefix/type conflict the producer abstains (``UNKNOWN`` at confidence 0.0) and
    keeps **both** signals as evidence — never a confident guess.
    """
    prefix = act_id_prefix(act_id)
    prefix_evidence = Evidence("act_id_prefix", f"act_id prefix={prefix!r}")

    mapped = _DOCUMENT_TYPE_CLASS.get(document_type) if document_type else None
    if mapped is None:
        return (
            DocumentClass.UNKNOWN,
            AuthorityRole.UNKNOWN,
            0.0,
            (
                Evidence(
                    "document_type",
                    f"document_type {document_type!r} has no broad-class mapping; "
                    f"abstaining",
                ),
                prefix_evidence,
            ),
        )

    broad_class, broad_role = mapped

    expected = _PREFIX_EXPECTED_CLASS.get(prefix) if prefix else None
    if expected is not None and expected != broad_class:
        return (
            DocumentClass.UNKNOWN,
            AuthorityRole.UNKNOWN,
            0.0,
            (
                Evidence(
                    "document_type",
                    f"document_type {document_type!r} => {broad_class}",
                ),
                Evidence(
                    "act_id_prefix",
                    f"prefix {prefix!r} expects {expected}; contradiction -> abstain",
                ),
            ),
        )

    # Refine a regulation into codified CFR vs. the Federal Register by prefix.
    doc_class, role = broad_class, broad_role
    refined = False
    if broad_class == DocumentClass.REGULATION:
        if prefix == "CFR":
            doc_class, role = (
                DocumentClass.CODIFIED_CFR,
                AuthorityRole.OPERATIVE_PRIMARY_LAW,
            )
            refined = True
        elif prefix == "FR":
            doc_class, role = (
                DocumentClass.FEDERAL_REGISTER,
                AuthorityRole.PROMULGATION_RECORD,
            )
            refined = True

    # ``document_type`` is what determined the class — it always carries the
    # confidence. The prefix evidence is only confident when it actually contributed
    # (refined a regulation, or confirmed a fixed expectation); an ambiguous/irrelevant
    # prefix (e.g. ``STATE``, which spans statutes *and* regulations) gets explicit
    # non-refining evidence with **no** confidence, so the record does not claim a
    # prefix "confirmed" a class it never constrained (M1A.5 review P3).
    dt_ev = Evidence(
        "document_type",
        f"document_type {document_type!r} => {broad_class}",
        confidence=1.0,
    )
    if refined:
        prefix_ev = Evidence(
            "act_id_prefix",
            f"prefix {prefix!r} refines regulation => {doc_class}/{role}",
            confidence=1.0,
        )
    elif expected is not None:  # expected == broad_class (a conflict already returned)
        prefix_ev = Evidence(
            "act_id_prefix",
            f"prefix {prefix!r} confirms {broad_class}",
            confidence=1.0,
        )
    else:
        prefix_ev = Evidence(
            "act_id_prefix",
            f"prefix {prefix!r} is non-refining/ambiguous; document_type alone set "
            f"the class",
        )
    return (doc_class, role, 1.0, (dt_ev, prefix_ev))


def classify_source_record(
    record: "CanonicalSourceRecord",
) -> DocumentClassificationAnnotation:
    """Produce a ``DocumentClassificationAnnotation`` for one source record.

    Reads the ``document_type`` and ``act_id`` source columns. Provenance anchors
    to the record's ``source_record_id`` (never to any identity key). Duck-typed on
    ``.source_record_id`` and ``.column(...)``, so it needs no import of the
    immutable-core module at runtime. The producer version is the module constant,
    **not** caller-overridable (M1A.5 closure A.5).
    """
    document_type = record.column("document_type")
    act_id = record.column("act_id")
    doc_class, role, confidence, evidence = classify(document_type, act_id)
    provenance = DerivedArtifactProvenance.build(
        ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION,
        source_record_inputs([record.source_record_id]),
        PRODUCER_NAME,
        PRODUCER_VERSION,
    )
    return DocumentClassificationAnnotation(
        provenance=provenance,
        document_class=doc_class,
        authority_role=role,
        confidence=confidence,
        evidence=evidence,
    )


def fr_default_off(annotation: DocumentClassificationAnnotation) -> bool:
    """Retrieval-policy hook: is this document excluded from present-law /
    exact-CFR resolution by default? True for the Federal Register."""
    return annotation.document_class == DocumentClass.FEDERAL_REGISTER
