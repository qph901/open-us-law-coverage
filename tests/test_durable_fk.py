"""M1A.5 headline acceptance — the durable-foreign-key test (against real producers).

From ``PROPOSAL.md`` ("Data contracts", "The durable-foreign-key rule") and the
M1A.5 closure decisions D1/B.3:

    Identity strategy v1 (key A) and v2 (key B) coexist over the same records;
    downstream provenance referencing those records stays valid; no immutable
    artifact is keyed by ``source_identity_key``; a membership change re-hashes the
    ``SourceIdentityGroup`` and every affected ``SourceIdentityMemberAnnotation``.
    Extend the same coexistence to assembly v1/v2 over the same members.

This is the invariant that keeps a *mistaken identity strategy from corrupting
provenance*: durable references anchor to ``source_record_id``, never to the
mutable ``source_identity_key``. The key/``legal_id`` live on a separate versioned
:class:`AssemblyIdentityAssociation` (review B3), not on the content-addressed
assembly.

**B.3: exercised against actual producer outputs**, not fabricated annotations. A
genuine **v1 vs v2 of one strategy** (``cfr_identity_v1``) over one valid member set
tests the strategy-improvement case: the real v1 producer vs. a v2 that makes a real
rule change (``provisional`` -> ``resolved``), so same producer name / same anchors,
different version + different conclusion body — coexisting without a payload collision.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from open_us_law_coverage.derived import (
    ArtifactInput,
    ArtifactType,
    AssemblyStatus,
    AssemblyStrategy,
    DerivedArtifactProvenance,
    Evidence,
    IdentityMember,
    IdentityScope,
    IdentityStatus,
    InputType,
    MemberRole,
    Operation,
    SegmentOrderConfidence,
    SegmentOrderMethod,
    SourceDocumentAssembly,
    SourceIdentityGroup,
    SourceIdentityMemberAnnotation,
    SourceIdentityResult,
    associate_assembly_with_identity,
    cfr_identity_group,
    check_payload_collisions,
    resolve_single_record_identity,
    source_record_inputs,
)
from open_us_law_coverage.derived.assembly import (
    TRIVIAL_PRODUCER_NAME,
    assemble_trivial_single_record,
    compute_assembled_text_hash,
)
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT

_CFR_ACT_ID = "CFR_T17_P240_S240.10b-5"
_CFR_KEY = f"US|regulations|{_CFR_ACT_ID}"


def _hash(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _members(n: int) -> list[IdentityMember]:
    return [
        IdentityMember(
            source_record_id=f"srr:sha256:r{i}",
            act_id=_CFR_ACT_ID,
            state="US",
            corpus="regulations",
            document_type="regulation",
            raw_text_hash=_hash(f"h{i}"),
            physical_row_ordinal=i,
        )
        for i in range(n)
    ]


def _cfr_group_at_version(
    members: list[IdentityMember], *, version: str, status: IdentityStatus
) -> SourceIdentityResult:
    """A hand-built ``cfr_identity_v1`` at an arbitrary producer version + rule outcome.

    Stands in for a legitimate future v2 of the *same* strategy: same producer name
    (``cfr_identity_v1``), a different ``producer_version``, and a genuine rule-shape
    difference (the multi-segment ``status``). Used only to exercise the version
    boundary the real code does not yet cross."""
    ids = tuple(sorted(m.source_record_id for m in members))
    group_prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_GROUP,
        source_record_inputs(ids),
        "cfr_identity_v1",
        version,
    )
    group = SourceIdentityGroup(
        provenance=group_prov,
        strategy_name="cfr_identity_v1",
        source_identity_key=_CFR_KEY,
        member_source_record_ids=ids,
        identity_scope=IdentityScope.SEGMENT,
        identity_status=status,
        confidence=1.0,
        evidence=(Evidence("version_boundary", f"cfr_identity_v1 producer v{version}"),),
    )
    anns = []
    for ordinal, m in enumerate(sorted(members, key=lambda x: x.source_record_id)):
        ann_prov = DerivedArtifactProvenance.build(
            ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION,
            (
                ArtifactInput(InputType.ANNOTATION, group.provenance.artifact_id),
                ArtifactInput(InputType.SOURCE_RECORD, m.source_record_id),
            ),
            "cfr_identity_v1",
            version,
        )
        anns.append(
            SourceIdentityMemberAnnotation(
                provenance=ann_prov,
                target_source_record_id=m.source_record_id,
                segment_ordinal=ordinal,
                segment_order_method=SegmentOrderMethod.PHYSICAL_ROW_ORDER,
                segment_order_confidence=SegmentOrderConfidence.SNAPSHOT_OBSERVED,
            )
        )
    return SourceIdentityResult(group=group, members=tuple(anns))


def test_identity_v1_v2_of_one_strategy_coexist_over_same_records():
    """A genuine M1A.5 B.3 version boundary: the real ``cfr_identity_v1`` producer
    (v1, ``provisional``) and a v2 of the *same* strategy that makes a real rule change
    (``resolved``) over one physical member set. Same producer name and same physical
    anchors; different ``producer_version`` and a different conclusion body — so two
    distinct ``artifact_id``s that coexist without a payload collision."""
    members = _members(3)
    v1 = cfr_identity_group(members)  # the real producer: version "1", provisional
    v2 = _cfr_group_at_version(members, version="2", status=IdentityStatus.RESOLVED)

    assert v1.group.provenance.producer_name == v2.group.provenance.producer_name
    assert v1.group.provenance.producer_version == "1"
    assert v2.group.provenance.producer_version == "2"
    assert v1.group.identity_status != v2.group.identity_status  # a real rule change
    assert v1.group.provenance.artifact_id != v2.group.provenance.artifact_id
    assert v1.group.payload_hash != v2.group.payload_hash  # different conclusion bodies

    anchors = tuple(sorted(m.source_record_id for m in members))
    assert v1.group.provenance.source_record_ids() == anchors
    assert v2.group.provenance.source_record_ids() == anchors
    # no immutable edge in either version references the mutable identity key.
    for result in (v1, v2):
        edges = {e.input_id for e in result.group.provenance.inputs}
        for m in result.members:
            edges |= {e.input_id for e in m.provenance.inputs}
        assert result.group.source_identity_key not in edges
    # both versions and all their member annotations coexist in one store.
    check_payload_collisions([v1.group, v2.group, *v1.members, *v2.members])


def test_no_provenance_edge_references_the_identity_key():
    members = _members(3)
    result = cfr_identity_group(members)
    key = result.group.source_identity_key
    all_edges = list(result.group.provenance.inputs)
    for m in result.members:
        all_edges.extend(m.provenance.inputs)
    edge_ids = {e.input_id for e in all_edges}
    assert key not in edge_ids
    # every edge is a source_record or an annotation (the group id), never the key.
    assert all(
        e.input_type in {InputType.SOURCE_RECORD, InputType.ANNOTATION}
        for e in all_edges
    )


def test_membership_change_rehashes_group_and_surviving_members():
    """D1 recompute frontier: dropping a member changes the group id AND every
    surviving member annotation (each names the group as an input)."""
    members = _members(3)
    full = cfr_identity_group(members)
    dropped = cfr_identity_group(members[:2])

    assert full.group.provenance.artifact_id != dropped.group.provenance.artifact_id
    full_ids = {
        m.target_source_record_id: m.provenance.artifact_id for m in full.members
    }
    dropped_ids = {
        m.target_source_record_id: m.provenance.artifact_id for m in dropped.members
    }
    for rid in dropped_ids:
        assert full_ids[rid] != dropped_ids[rid]


def test_downstream_assembly_anchors_to_source_record_only(
    statutes_fixture_parquet: Path,
):
    records = read_source_records(statutes_fixture_parquet, SNAPSHOT)
    rec = records[0]
    ident = resolve_single_record_identity(rec)
    assert ident is not None
    downstream = assemble_trivial_single_record(rec)
    edge_ids = {e.input_id for e in downstream.provenance.inputs}
    assert ident.group.source_identity_key not in edge_ids
    assert all(
        e.input_type == InputType.SOURCE_RECORD for e in downstream.provenance.inputs
    )


def test_assembly_id_is_invariant_to_the_identity_key(fixture_parquet: Path):
    """Review B3: the same assembly body has one ``artifact_id`` regardless of which
    identity key associates with it — the key is not a field on the assembly."""
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    asm = assemble_trivial_single_record(rec)
    assoc_a = associate_assembly_with_identity(
        "KEY_A", asm, strategy_name="cfr_identity_v1", strategy_version="1"
    )
    assoc_b = associate_assembly_with_identity(
        "KEY_B", asm, strategy_name="cfr_identity_v2", strategy_version="2"
    )
    assert assoc_a.source_identity_key != assoc_b.source_identity_key
    assert assoc_a.assembly_artifact_id == assoc_b.assembly_artifact_id


def test_assembly_v1_v2_coexist_over_same_members(fixture_parquet: Path):
    """M1A.5 A.5: a genuine shape difference — a legacy v1-labeled fixture vs. the
    real v2 producer over one record — not two labels of one body."""
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    v2 = assemble_trivial_single_record(rec)

    legacy_prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY,
        source_record_inputs([rec.source_record_id]),
        TRIVIAL_PRODUCER_NAME,
        "1",
    )
    text = rec.raw_text if rec.raw_text is not None else "x"
    v1 = SourceDocumentAssembly(
        provenance=legacy_prov,
        member_source_record_ids=(rec.source_record_id,),
        member_roles=(MemberRole.PRIMARY,),
        operations=(Operation.KEEP,),
        assembly_strategy=AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V1,
        assembly_status=AssemblyStatus.COMPLETE,
        assembled_text=text,
        assembled_text_hash=compute_assembled_text_hash(text),
    )
    assert v1.provenance.artifact_id != v2.provenance.artifact_id
    assert v1.provenance.source_record_ids() == v2.provenance.source_record_ids()
    check_payload_collisions([v1, v2])


def test_immutable_core_carries_no_identity_key(fixture_parquet: Path):
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    assert not hasattr(rec, "source_identity_key")
    assert "source_identity_key" not in rec.original_columns
