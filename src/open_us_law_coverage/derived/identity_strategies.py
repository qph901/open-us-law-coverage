"""Concrete ``SourceIdentityStrategy`` producers (M1A.5 closure, NEXT.md Phase B).

A strategy *implementation* is corpus-specific; the artifact *interfaces*
(:mod:`.identity`) are universal (the M0.5B3 rule). These producers emit the D1
shape — a :class:`SourceIdentityGroup` content-addressed by the complete member set
plus one :class:`SourceIdentityMemberAnnotation` per member — and never compose text
(that is :mod:`.assembly`).

Two families:

* **1:1 strategies** (B.1) — ``usc_act_id_v1`` / ``state_statute_act_id_v1`` /
  ``constitution_act_id_v1``. Each row is its own document (``act_id`` is 100%
  unique in these corpora, M0/M0.5A), so each emits a **single-member** group:
  ``identity_status = resolved``, ``segment_order_method = single_record``,
  ``segment_order_confidence = not_applicable``. This is the degenerate case of the
  group shape — the same object a multi-member group collapses to at size one.

* **Regulations collision strategies** (B.2) — ``cfr_identity_v1`` and
  ``federal_register_document_v1`` over ``us_federal_regulations`` (the only file
  where ``act_id`` repeats, M0). They emit **multi-member** groups over the rows
  that share an ``act_id``, preserving the frozen M0.5A.1 semantics *without
  exception*: ``segment_ordinal`` is snapshot-observed **physical row order** and
  never a reading order; FR rows are a co-numbered **numbering bucket**, never one
  document, so the strategy marks them ``ambiguous`` and identity never concatenates
  them; CFR collisions are a ``provisional`` multi-**segment** candidate that
  assembly/anatomy (CFR-A2) must confirm before any text is composed.

**OOM invariant (CLAUDE.md).** The collision producers take a lightweight
:class:`IdentityMember` view — ``source_record_id`` / ``act_id`` / ``raw_text_hash``
/ ``physical_row_ordinal`` — **never** the ``raw_text`` bytes, so a full-file scan
that buckets ~290k regulation rows by ``act_id`` holds only the small fields, not
the 11 GB ``text`` column. Build one from a streamed record with
:func:`identity_member`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

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
    source_record_inputs,
)

if TYPE_CHECKING:
    from open_us_law_coverage.source_record import CanonicalSourceRecord


USC_ACT_ID_V1 = "usc_act_id_v1"
STATE_STATUTE_ACT_ID_V1 = "state_statute_act_id_v1"
CONSTITUTION_ACT_ID_V1 = "constitution_act_id_v1"
CFR_IDENTITY_V1 = "cfr_identity_v1"
FEDERAL_REGISTER_DOCUMENT_V1 = "federal_register_document_v1"
STATE_REGULATION_V1 = "state_regulation_v1"

STRATEGY_VERSION = "1"


def act_id_prefix(act_id: str | None) -> str:
    """The namespace prefix of an ``act_id`` (``CFR_T17_..`` -> ``CFR``)."""
    return (act_id or "").split("_", 1)[0]


@dataclass(frozen=True, slots=True)
class IdentityMember:
    """The small projection of a source record an identity strategy needs.

    Deliberately excludes ``raw_text`` (see the module OOM note): a strategy keys and
    orders members and fingerprints their content by ``raw_text_hash``, never by the
    bytes. Build one with :func:`identity_member`.
    """

    source_record_id: str
    act_id: str | None
    state: str | None
    corpus: str
    document_type: str | None
    raw_text_hash: str | None
    physical_row_ordinal: int


def corpus_of_source_file(source_file: str) -> str:
    """The corpus segment of an Open US Law filename: ``us_ca_statutes.parquet`` ->
    ``statutes``. Corpus is not a column, so it is recovered from the file name (the
    ``(state, corpus, act_id)`` uniqueness key, PROPOSAL.md)."""
    stem = Path(source_file).stem
    parts = stem.split("_", 2)
    return parts[2] if len(parts) == 3 else stem


def identity_member(record: "CanonicalSourceRecord") -> IdentityMember:
    """Project a full record down to the fields a strategy reads (no ``raw_text``)."""
    return IdentityMember(
        source_record_id=record.source_record_id,
        act_id=record.column("act_id"),
        state=record.column("state"),
        corpus=corpus_of_source_file(record.source_file),
        document_type=record.column("document_type"),
        raw_text_hash=record.raw_text_hash,
        physical_row_ordinal=record.physical_row_ordinal,
    )


def _identity_key(member: IdentityMember) -> str:
    """The mutable ``source_identity_key`` — ``(state, corpus, act_id)`` (PROPOSAL.md).
    Never anchored to by a durable FK; it only groups."""
    return f"{member.state}|{member.corpus}|{member.act_id}"


def _segment_fingerprint(member: IdentityMember, occurrence_index: int) -> str:
    """``(act_id, raw_text_hash, occurrence_index)`` — content-addressed; the
    occurrence index only disambiguates byte-identical duplicate rows within the
    group (M0.5A.1), which are semantically interchangeable."""
    return f"{member.act_id}|{member.raw_text_hash}|{occurrence_index}"


def _build_group(
    members: Sequence[IdentityMember],
    *,
    strategy_name: str,
    key: str,
    scope: IdentityScope,
    status: IdentityStatus,
    confidence: float,
    evidence: tuple[Evidence, ...],
) -> SourceIdentityGroup:
    canonical_ids = tuple(sorted(m.source_record_id for m in members))
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_GROUP,
        source_record_inputs(canonical_ids),
        strategy_name,
        STRATEGY_VERSION,
    )
    return SourceIdentityGroup(
        provenance=prov,
        strategy_name=strategy_name,
        source_identity_key=key,
        member_source_record_ids=canonical_ids,
        identity_scope=scope,
        identity_status=status,
        confidence=confidence,
        evidence=evidence,
    )


def _member_annotation(
    group: SourceIdentityGroup,
    member: IdentityMember,
    *,
    strategy_name: str,
    segment_ordinal: int,
    occurrence_index: int,
    method: SegmentOrderMethod,
    confidence: SegmentOrderConfidence,
) -> SourceIdentityMemberAnnotation:
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION,
        (
            ArtifactInput(InputType.ANNOTATION, group.provenance.artifact_id),
            ArtifactInput(InputType.SOURCE_RECORD, member.source_record_id),
        ),
        strategy_name,
        STRATEGY_VERSION,
    )
    return SourceIdentityMemberAnnotation(
        provenance=prov,
        target_source_record_id=member.source_record_id,
        segment_fingerprint=_segment_fingerprint(member, occurrence_index),
        segment_ordinal=segment_ordinal,
        segment_order_method=method,
        segment_order_confidence=confidence,
    )


# ---------------------------------------------------------------------------
# B.1 — the 1:1 strategies (single-member groups).
# ---------------------------------------------------------------------------

def _single_member_identity(
    member: IdentityMember, *, strategy_name: str, evidence_detail: str
) -> SourceIdentityResult:
    group = _build_group(
        [member],
        strategy_name=strategy_name,
        key=_identity_key(member),
        scope=IdentityScope.DOCUMENT,
        status=IdentityStatus.RESOLVED,
        confidence=1.0,
        evidence=(Evidence("single_record_group", evidence_detail, confidence=1.0),),
    )
    annotation = _member_annotation(
        group,
        member,
        strategy_name=strategy_name,
        segment_ordinal=0,
        occurrence_index=0,
        method=SegmentOrderMethod.SINGLE_RECORD,
        confidence=SegmentOrderConfidence.NOT_APPLICABLE,
    )
    return SourceIdentityResult(group=group, members=(annotation,))


def usc_act_id_identity(record: "CanonicalSourceRecord") -> SourceIdentityResult:
    """``usc_act_id_v1`` — one USC section row is one document (``act_id`` unique)."""
    return _single_member_identity(
        identity_member(record),
        strategy_name=USC_ACT_ID_V1,
        evidence_detail="USC act_id is unique per section; 1:1 source->document",
    )


def state_statute_act_id_identity(
    record: "CanonicalSourceRecord",
) -> SourceIdentityResult:
    """``state_statute_act_id_v1`` — one state statute row is one document."""
    return _single_member_identity(
        identity_member(record),
        strategy_name=STATE_STATUTE_ACT_ID_V1,
        evidence_detail="state statute act_id is unique per provision; 1:1",
    )


def constitution_identity(record: "CanonicalSourceRecord") -> SourceIdentityResult:
    """``constitution_act_id_v1`` — one constitution provision row is one document."""
    return _single_member_identity(
        identity_member(record),
        strategy_name=CONSTITUTION_ACT_ID_V1,
        evidence_detail="constitution act_id is unique per provision; 1:1",
    )


def resolve_single_record_identity(
    record: "CanonicalSourceRecord",
) -> SourceIdentityResult | None:
    """Dispatch a record to its 1:1 strategy, or ``None`` if it is not a 1:1 case.

    Regulations (``CFR_*`` / ``FR_*``) return ``None`` here — they are grouped by the
    collision strategies (B.2), which need the sibling set, not a per-record call.
    """
    member = identity_member(record)
    prefix = (member.act_id or "").split("_", 1)[0]
    document_type = member.document_type
    if prefix == "USC":
        return usc_act_id_identity(record)
    if document_type == "constitution" or prefix in {"SCONST", "CONST"}:
        return constitution_identity(record)
    if document_type == "statute" or prefix == "STATE":
        return state_statute_act_id_identity(record)
    return None


# ---------------------------------------------------------------------------
# B.2 — the regulations collision strategies (multi-member groups).
# ---------------------------------------------------------------------------

def _regulations_identity_group(
    members: Sequence[IdentityMember],
    *,
    strategy_name: str,
    multi_scope: IdentityScope,
    multi_status: IdentityStatus,
    multi_evidence_detail: str,
) -> SourceIdentityResult:
    """Group rows that share an ``act_id`` into one identity group.

    A single-row ``act_id`` is the degenerate 1:1 case (``resolved`` document,
    ``single_record``). A multi-row ``act_id`` is a candidate group whose members are
    ordered by **physical row order only** (M0.5A.1) — ``segment_ordinal`` is
    snapshot-observed, never a reading order. Identity groups and characterizes; it
    does **not** compose (FR is never concatenated — that abstention lives in
    assembly, gated by this group's ``ambiguous`` status).
    """
    if not members:
        raise ValueError("a regulations identity group needs at least one member")
    key = _identity_key(members[0])

    if len(members) == 1:
        return _single_member_identity(
            members[0],
            strategy_name=strategy_name,
            evidence_detail="single-row act_id; 1:1 source->document",
        )

    # Physical row order is the only defensible order (M0.5A.1). Ties (identical
    # ordinal should not happen within a file, but be deterministic anyway) break by
    # source_record_id.
    ordered = sorted(members, key=lambda m: (m.physical_row_ordinal, m.source_record_id))
    group = _build_group(
        ordered,
        strategy_name=strategy_name,
        key=key,
        scope=multi_scope,
        status=multi_status,
        confidence=1.0,
        evidence=(
            Evidence(
                "act_id_collision_group",
                f"{len(ordered)} rows share act_id {members[0].act_id!r}; "
                + multi_evidence_detail,
                confidence=1.0,
            ),
            Evidence(
                "segment_order",
                "segment_ordinal is snapshot-observed physical row order only "
                "(M0.5A.1); not a reading order",
            ),
        ),
    )

    # occurrence_index disambiguates byte-identical duplicate rows within the group.
    seen_hash: dict[str | None, int] = {}
    annotations = []
    for ordinal, member in enumerate(ordered):
        occ = seen_hash.get(member.raw_text_hash, 0)
        seen_hash[member.raw_text_hash] = occ + 1
        annotations.append(
            _member_annotation(
                group,
                member,
                strategy_name=strategy_name,
                segment_ordinal=ordinal,
                occurrence_index=occ,
                method=SegmentOrderMethod.PHYSICAL_ROW_ORDER,
                confidence=SegmentOrderConfidence.SNAPSHOT_OBSERVED,
            )
        )
    return SourceIdentityResult(group=group, members=tuple(annotations))


def cfr_identity_group(members: Sequence[IdentityMember]) -> SourceIdentityResult:
    """``cfr_identity_v1`` — rows sharing a ``CFR_*`` ``act_id``.

    A multi-row CFR ``act_id`` is a **provisional multi-segment** candidate: it may be
    the pieces of one codified section, but that is not proven from the snapshot alone
    (needs the eCFR oracle, CFR-A1/A2). So the group is ``provisional`` at
    ``segment`` scope — assembly decides whether to compose, and abstains otherwise.
    """
    return _regulations_identity_group(
        members,
        strategy_name=CFR_IDENTITY_V1,
        multi_scope=IdentityScope.SEGMENT,
        multi_status=IdentityStatus.PROVISIONAL,
        multi_evidence_detail="provisional multi-segment CFR candidate; assembly to confirm",
    )


def federal_register_document_group(
    members: Sequence[IdentityMember],
) -> SourceIdentityResult:
    """``federal_register_document_v1`` — rows sharing an ``FR_*`` ``act_id``.

    M0.5A.1 established these are **co-numbered distinct captures**, not one document:
    scattered rows, no ordered segmentation, no valid concatenation. So a multi-row FR
    ``act_id`` is a ``numbering_bucket`` marked **ambiguous** — the members share a
    namespace key, and identity refuses to claim they compose one document. Assembly
    reads this ``ambiguous`` status and abstains (returns ``source_url``, never a
    concatenation).
    """
    return _regulations_identity_group(
        members,
        strategy_name=FEDERAL_REGISTER_DOCUMENT_V1,
        multi_scope=IdentityScope.NUMBERING_BUCKET,
        multi_status=IdentityStatus.AMBIGUOUS,
        multi_evidence_detail=(
            "co-numbered distinct FR captures (M0.5A.1); shared namespace, not one "
            "document; do not compose"
        ),
    )


def state_regulation_identity_group(
    members: Sequence[IdentityMember],
) -> SourceIdentityResult:
    """``state_regulation_v1`` — rows sharing a ``STATE_*`` **regulation** ``act_id``.

    The full-snapshot manifest (C.3) surfaced that ``act_id`` collisions are **not**
    federal-only: state administrative-code corpora (OH, IL, KY, MD, ME, MN) also
    repeat an ``act_id`` across rows. Like CFR (and unlike FR), these are a
    ``provisional`` multi-**segment** candidate — pieces of one codified rule section
    that assembly/anatomy must confirm before any text is composed. Same abstention
    discipline: identity groups, it does not concatenate.
    """
    return _regulations_identity_group(
        members,
        strategy_name=STATE_REGULATION_V1,
        multi_scope=IdentityScope.SEGMENT,
        multi_status=IdentityStatus.PROVISIONAL,
        multi_evidence_detail=(
            "provisional multi-segment state-regulation candidate; assembly to confirm"
        ),
    )


def regulations_identity_group(
    members: Sequence[IdentityMember],
) -> SourceIdentityResult:
    """Route a regulations collision group to its strategy by ``act_id`` namespace:
    ``FR_*`` -> Federal Register (ambiguous), ``CFR_*`` -> codified CFR (provisional),
    anything else (``STATE_*`` administrative codes) -> state regulation (provisional).
    """
    if not members:
        raise ValueError("a regulations identity group needs at least one member")
    prefix = act_id_prefix(members[0].act_id)
    if prefix == "FR":
        return federal_register_document_group(members)
    if prefix == "CFR":
        return cfr_identity_group(members)
    return state_regulation_identity_group(members)
