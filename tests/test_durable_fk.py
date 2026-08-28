"""M1A.5 headline acceptance — the durable-foreign-key test.

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

Phase A exercises the property against fabricated group/member artifacts (the shape
is what is under test here); ``test_identity_group.py`` and the Phase B producer
suites exercise it against real producer outputs.
"""

from __future__ import annotations

from pathlib import Path

from open_us_law_coverage.derived import (
    ArtifactInput,
    ArtifactType,
    AssemblyStrategy,
    DerivedArtifactProvenance,
    Evidence,
    IdentityScope,
    IdentityStatus,
    InputType,
    SourceIdentityGroup,
    SourceIdentityMemberAnnotation,
    SourceIdentityResult,
    associate_assembly_with_identity,
    check_payload_collisions,
    source_record_inputs,
)
from open_us_law_coverage.derived.assembly import (
    TRIVIAL_PRODUCER_NAME,
    assemble_trivial_single_record,
    compute_assembled_text_hash,
)
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT


def _identity_result(
    members, *, strategy: str, key: str, producer_version: str
) -> SourceIdentityResult:
    """A fabricated identity result (group + one annotation per member) in the D1
    shape: the group is content-addressed by the complete member set, each member
    annotation names the group and its own record."""
    canonical = tuple(sorted(members))
    group_prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_GROUP,
        source_record_inputs(canonical),
        "identity_strategy",
        producer_version,
    )
    group = SourceIdentityGroup(
        provenance=group_prov,
        strategy_name=strategy,
        source_identity_key=key,
        member_source_record_ids=canonical,
        identity_scope=IdentityScope.DOCUMENT,
        identity_status=IdentityStatus.RESOLVED,
        confidence=1.0,
        evidence=(Evidence("test", "synthetic group"),),
    )
    annotations = tuple(
        SourceIdentityMemberAnnotation(
            provenance=DerivedArtifactProvenance.build(
                ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION,
                (
                    ArtifactInput(InputType.ANNOTATION, group.provenance.artifact_id),
                    ArtifactInput(InputType.SOURCE_RECORD, m),
                ),
                "identity_strategy",
                producer_version,
            ),
            target_source_record_id=m,
        )
        for m in canonical
    )
    return SourceIdentityResult(group=group, members=annotations)


def test_identity_v1_v2_coexist_over_same_records(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    members = [r.source_record_id for r in records[:3]]

    v1 = _identity_result(members, strategy="cfr_identity_v1", key="KEY_A", producer_version="1")
    v2 = _identity_result(members, strategy="cfr_identity_v2", key="KEY_B", producer_version="2")

    # Two strategies, two keys, one member set — both are valid at once.
    assert v1.group.source_identity_key != v2.group.source_identity_key
    assert v1.group.provenance.artifact_id != v2.group.provenance.artifact_id
    # Both still point at exactly the same physical rows.
    assert set(v1.group.provenance.source_record_ids()) == set(members)
    assert set(v2.group.provenance.source_record_ids()) == set(members)
    # No collision in a shared store.
    check_payload_collisions([v1.group, v2.group, *v1.members, *v2.members])


def test_membership_change_rehashes_group_and_members(fixture_parquet: Path):
    """D1 recompute frontier: dropping a member changes the group id AND every
    surviving member annotation's id (they name the group as an input)."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    members = [r.source_record_id for r in records[:3]]

    full = _identity_result(members, strategy="cfr_identity_v1", key="K", producer_version="1")
    dropped = _identity_result(members[:2], strategy="cfr_identity_v1", key="K", producer_version="1")

    assert full.group.provenance.artifact_id != dropped.group.provenance.artifact_id
    # The two members that survive get NEW annotation ids because the group input changed.
    surviving = set(members[:2])
    full_ids = {
        a.target_source_record_id: a.provenance.artifact_id
        for a in full.members
        if a.target_source_record_id in surviving
    }
    dropped_ids = {
        a.target_source_record_id: a.provenance.artifact_id for a in dropped.members
    }
    for rid in surviving:
        assert full_ids[rid] != dropped_ids[rid]


def test_no_provenance_edge_references_the_identity_key(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    members = [r.source_record_id for r in records[:3]]
    ident = _identity_result(members, strategy="cfr_identity_v1", key="KEY_A", producer_version="1")

    # A downstream assembly over the group anchors to source_record_ids, never to
    # the (mutable) source_identity_key.
    downstream = assemble_trivial_single_record(records[0])
    edge_ids = {e.input_id for e in downstream.provenance.inputs}
    assert ident.group.source_identity_key not in edge_ids
    assert all(e.input_type == InputType.SOURCE_RECORD for e in downstream.provenance.inputs)


def test_assembly_id_is_invariant_to_the_identity_key(fixture_parquet: Path):
    """The sharp edge of the rule (review B3): the same assembly body has one
    ``artifact_id`` regardless of which identity key associates with it — because
    the key is no longer a field on the content-addressed assembly. Key A and key B
    associate with the *same* assembly id."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    rec = records[0]
    asm = assemble_trivial_single_record(rec)

    assoc_a = associate_assembly_with_identity(
        "KEY_A", asm, strategy_name="cfr_identity_v1", strategy_version="1"
    )
    assoc_b = associate_assembly_with_identity(
        "KEY_B", asm, strategy_name="cfr_identity_v2", strategy_version="2"
    )
    assert assoc_a.source_identity_key != assoc_b.source_identity_key
    # One immutable assembly body -> one artifact id under both keys.
    assert assoc_a.assembly_artifact_id == assoc_b.assembly_artifact_id


def test_assembly_v1_v2_coexist_over_same_members(fixture_parquet: Path):
    """NEXT.md A.5: exercised against a genuine shape difference — a legacy v1-labeled
    fixture vs. the real v2 producer — not two labels of one body (the version is no
    longer caller-overridable)."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    rec = records[0]
    v2 = assemble_trivial_single_record(rec)

    from open_us_law_coverage.derived import (
        AssemblyStatus,
        MemberRole,
        Operation,
        SourceDocumentAssembly,
    )

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
    # Different producer versions -> distinct artifacts, same physical anchor.
    assert v1.provenance.artifact_id != v2.provenance.artifact_id
    assert v1.provenance.source_record_ids() == v2.provenance.source_record_ids()


def test_immutable_core_carries_no_identity_key(fixture_parquet: Path):
    """No ``CanonicalSourceRecord`` field is derived from an identity key — the
    core cannot be corrupted by an identity-strategy change."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    rec = records[0]
    assert not hasattr(rec, "source_identity_key")
    assert "source_identity_key" not in rec.original_columns
