"""M1A.5 headline acceptance — the durable-foreign-key test.

From ``PROPOSAL.md`` ("Data contracts", "The durable-foreign-key rule"):

    Identity strategy v1 (key A) and v2 (key B) coexist over the same records;
    downstream provenance referencing those records stays valid; no immutable
    artifact is keyed by ``source_identity_key``. Extend the same coexistence
    test to assembly v1/v2 over the same members.

This is the invariant that keeps a *mistaken identity strategy from corrupting
provenance*: durable references anchor to ``source_record_id``, never to the
mutable ``source_identity_key``. The key/``legal_id`` live on a separate versioned
:class:`AssemblyIdentityAssociation` (review B3), not on the content-addressed
assembly.
"""

from __future__ import annotations

from pathlib import Path

from open_us_law_coverage.derived import (
    ArtifactType,
    DerivedArtifactProvenance,
    Evidence,
    IdentityScope,
    IdentityStatus,
    InputType,
    SourceIdentityAnnotation,
    associate_assembly_with_identity,
    source_record_inputs,
)
from open_us_law_coverage.derived.assembly import assemble_trivial_single_record
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT


def _identity(members, *, strategy: str, key: str, producer_version: str) -> SourceIdentityAnnotation:
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_ANNOTATION,
        source_record_inputs(members),
        "identity_strategy",
        producer_version,
    )
    return SourceIdentityAnnotation(
        provenance=prov,
        strategy_name=strategy,
        source_identity_key=key,
        member_source_record_ids=tuple(members),
        identity_scope=IdentityScope.DOCUMENT,
        identity_status=IdentityStatus.RESOLVED,
        confidence=1.0,
        evidence=(Evidence("test", "synthetic group"),),
    )


def test_identity_v1_v2_coexist_over_same_records(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    members = [r.source_record_id for r in records[:3]]

    v1 = _identity(members, strategy="cfr_identity_v1", key="KEY_A", producer_version="1")
    v2 = _identity(members, strategy="cfr_identity_v2", key="KEY_B", producer_version="2")

    # Two strategies, two keys, one member set — both are valid at once.
    assert v1.source_identity_key != v2.source_identity_key
    assert v1.provenance.artifact_id != v2.provenance.artifact_id
    # Both still point at exactly the same physical rows (stored order is
    # canonical, so compare as sets).
    assert set(v1.provenance.source_record_ids()) == set(members)
    assert set(v2.provenance.source_record_ids()) == set(members)


def test_no_provenance_edge_references_the_identity_key(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    members = [r.source_record_id for r in records[:3]]
    ident = _identity(members, strategy="cfr_identity_v1", key="KEY_A", producer_version="1")

    # A downstream assembly over the group anchors to source_record_ids, never to
    # the (mutable) source_identity_key.
    downstream = assemble_trivial_single_record(records[0])
    edge_ids = {e.input_id for e in downstream.provenance.inputs}
    assert ident.source_identity_key not in edge_ids
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
    records = read_source_records(fixture_parquet, SNAPSHOT)
    rec = records[0]
    v1 = assemble_trivial_single_record(rec, producer_version="1")
    v2 = assemble_trivial_single_record(rec, producer_version="2")
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
