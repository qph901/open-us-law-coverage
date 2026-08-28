"""M1A.5 headline acceptance — the durable-foreign-key test (against real producers).

From ``PROPOSAL.md`` ("Data contracts", "The durable-foreign-key rule") and
``NEXT.md`` (D1, B.3):

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

**B.3: exercised against actual producer outputs**, not fabricated annotations. Two
real strategies over one member set stand in for the strategy-improvement (v1->v2)
case: different strategy identity => different key and group id, same physical
anchors.
"""

from __future__ import annotations

from pathlib import Path

from open_us_law_coverage.derived import (
    ArtifactType,
    AssemblyStatus,
    AssemblyStrategy,
    DerivedArtifactProvenance,
    IdentityMember,
    InputType,
    MemberRole,
    Operation,
    SourceDocumentAssembly,
    associate_assembly_with_identity,
    cfr_identity_group,
    check_payload_collisions,
    federal_register_document_group,
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


def _members(n: int) -> list[IdentityMember]:
    return [
        IdentityMember(
            source_record_id=f"srr:sha256:r{i}",
            act_id="X_1",
            state="US",
            corpus="regulations",
            document_type="regulation",
            raw_text_hash=f"h{i}",
            physical_row_ordinal=i,
        )
        for i in range(n)
    ]


def test_two_real_strategies_coexist_over_same_records():
    """Strategy A (cfr_identity_v1) and strategy B (federal_register_document_v1) over
    one member set stand in for the strategy-improvement (v1->v2) case: two distinct
    group artifacts (different producer identity => different ``artifact_id`` and a
    different conclusion body) over one physical anchor set, both valid at once. The
    ``source_identity_key`` is strategy-independent by design — the durable-FK
    guarantee is not that the key differs but that no immutable artifact hashes it."""
    members = _members(3)
    a = cfr_identity_group(members)
    b = federal_register_document_group(members)

    assert a.group.provenance.artifact_id != b.group.provenance.artifact_id
    assert a.group.payload_hash != b.group.payload_hash  # different conclusion bodies
    anchors = tuple(sorted(m.source_record_id for m in members))
    assert a.group.provenance.source_record_ids() == anchors
    assert b.group.provenance.source_record_ids() == anchors
    check_payload_collisions([a.group, b.group, *a.members, *b.members])


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


def test_downstream_assembly_anchors_to_source_record_only(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
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
    """NEXT.md A.5: a genuine shape difference — a legacy v1-labeled fixture vs. the
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
