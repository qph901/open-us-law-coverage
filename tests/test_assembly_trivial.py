"""M1A.5 acceptance — the ``trivial_single_record_v2`` assembly producer.

Covers review B3 (no ``source_identity_key`` on the content-addressed artifact; a
separate versioned association carries the key/``legal_id``), P1 (null source text
is ``NONCOMPOSABLE``, never a complete empty document; v2 producer), and the P2
model invariants (provenance type + member/input agreement, full status/text matrix).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from open_us_law_coverage.derived import (
    ArtifactType,
    AssemblyStatus,
    AssemblyStrategy,
    DerivedArtifactProvenance,
    MemberRole,
    Operation,
    SourceDocumentAssembly,
    associate_assembly_with_identity,
    source_record_inputs,
)
from open_us_law_coverage.derived.assembly import (
    assemble_trivial_single_record,
    compute_assembled_text_hash,
)
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT


def test_trivial_assembly_keeps_raw_text_verbatim(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    for rec in records:
        asm = assemble_trivial_single_record(rec)
        if rec.raw_text is None:
            continue  # covered by test_null_text_is_noncomposable
        # not one byte invented or dropped.
        assert asm.assembled_text == rec.raw_text
        assert asm.assembled_text_hash == compute_assembled_text_hash(rec.raw_text)
        assert asm.assembly_strategy == AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V2
        assert asm.provenance.producer_version == "2"
        assert asm.assembly_status == AssemblyStatus.COMPLETE
        assert asm.operations == (Operation.KEEP,)
        assert asm.member_roles == (MemberRole.PRIMARY,)
        assert asm.member_source_record_ids == (rec.source_record_id,)
        assert asm.confidence == 1.0


def test_null_text_is_noncomposable(fixture_parquet: Path):
    """P1: a null source body cannot be a complete assembly."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    null_recs = [r for r in records if r.raw_text is None]
    assert null_recs  # the fixture has one
    for rec in null_recs:
        asm = assemble_trivial_single_record(rec)
        assert asm.assembly_status == AssemblyStatus.NONCOMPOSABLE
        assert asm.assembled_text is None
        assert asm.assembled_text_hash is None


def test_empty_string_is_complete(fixture_parquet: Path):
    """P1 corollary: ``""`` is a valid, complete empty provision (distinct from null)."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    empties = [r for r in records if r.raw_text == ""]
    assert empties
    for rec in empties:
        asm = assemble_trivial_single_record(rec)
        assert asm.assembly_status == AssemblyStatus.COMPLETE
        assert asm.assembled_text == ""


def test_complete_implies_returnable_text(fixture_parquet: Path):
    """The eligibility invariant: complete => non-null, returnable text."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    for rec in records:
        asm = assemble_trivial_single_record(rec)
        if asm.assembly_status == AssemblyStatus.COMPLETE:
            assert asm.assembled_text is not None


def test_assembly_carries_no_identity_key(fixture_parquet: Path):
    """B3: the content-addressed assembly has no ``source_identity_key`` field."""
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    asm = assemble_trivial_single_record(rec)
    assert not hasattr(asm, "source_identity_key")


def test_identity_association_is_separate_and_does_not_change_the_assembly(fixture_parquet: Path):
    """B3: key A and key B may both associate with one assembly id without changing
    the assembly body."""
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    asm = assemble_trivial_single_record(rec)

    assoc_a = associate_assembly_with_identity(
        "KEY_A", asm, strategy_name="cfr_identity_v1", strategy_version="1", legal_id="LEGAL_1"
    )
    assoc_b = associate_assembly_with_identity(
        "KEY_B", asm, strategy_name="cfr_identity_v2", strategy_version="2", legal_id="LEGAL_1"
    )
    assert assoc_a.source_identity_key != assoc_b.source_identity_key
    assert assoc_a.assembly_artifact_id == assoc_b.assembly_artifact_id == asm.provenance.artifact_id
    assert assoc_a.legal_id == "LEGAL_1"


def test_identity_association_is_a_governed_derived_artifact(fixture_parquet: Path):
    """Finding P1-4: the association is a first-class derived artifact — it carries
    provenance (one ``assembly`` edge) and a validated ``payload_hash``, so the
    collision tripwire covers it. Two keys over one assembly get distinct
    ``artifact_id``s (the key is folded into ``config_hash``, never a provenance edge),
    so they coexist without a payload collision."""
    from open_us_law_coverage.derived import (
        ArtifactType,
        InputType,
        check_payload_collisions,
    )

    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    asm = assemble_trivial_single_record(rec)
    a = associate_assembly_with_identity(
        "KEY_A", asm, strategy_name="cfr_identity_v1", strategy_version="1"
    )
    b = associate_assembly_with_identity(
        "KEY_B", asm, strategy_name="cfr_identity_v1", strategy_version="1"
    )
    # a governed artifact: right type, a validated payload hash, one assembly edge.
    assert a.provenance.artifact_type == ArtifactType.ASSEMBLY_IDENTITY_ASSOCIATION
    assert a.payload_hash and b.payload_hash
    assert a.provenance.input_ids_of(InputType.ASSEMBLY) == (asm.provenance.artifact_id,)
    # the mutable key is never a provenance edge (durable-FK rule)…
    assert "KEY_A" not in {e.input_id for e in a.provenance.inputs}
    # …but it distinguishes the two associations, so no id collision over one assembly.
    assert a.provenance.artifact_id != b.provenance.artifact_id
    check_payload_collisions([a, b])


def test_corrected_producer_is_v2_and_cannot_share_v1_artifact_id(fixture_parquet: Path):
    """Review P1 / M1A.5 A.5: the corrected producer changed the object it derives
    from a record (no identity key, added confidence, null->noncomposable). It is
    published as v2, so it can never collide with the deprecated v1 artifact id.

    The producer version is no longer caller-overridable, so this exercises a
    *genuine* legacy shape difference: a hand-built v1-labeled legacy fixture vs. the
    real v2 producer output over the same record — a different artifact id, and no
    payload collision (distinct ids, so the tripwire has nothing to fire on)."""
    from open_us_law_coverage.derived import check_payload_collisions
    from open_us_law_coverage.derived.assembly import (
        TRIVIAL_PRODUCER_NAME,
        TRIVIAL_PRODUCER_VERSION,
    )

    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    corrected = assemble_trivial_single_record(rec)
    assert TRIVIAL_PRODUCER_VERSION == "2"
    assert corrected.provenance.producer_version == "2"
    assert corrected.assembly_strategy == AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V2

    # A legacy v1-labeled artifact over the same record: built at producer version
    # "1" with the deprecated strategy label. Its derivation address differs from v2,
    # so old and corrected semantics can never share one id.
    legacy_prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY,
        source_record_inputs([rec.source_record_id]),
        TRIVIAL_PRODUCER_NAME,
        "1",
    )
    legacy_v1 = _assembly(
        rec,
        legacy_prov,
        assembly_strategy=AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V1,
    )
    assert corrected.provenance.artifact_id != legacy_v1.provenance.artifact_id
    # Both coexist in one store without tripping the equal-id/unequal-payload check.
    check_payload_collisions([corrected, legacy_v1])


def test_assembly_provenance_anchors_to_source_record(fixture_parquet: Path):
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    asm = assemble_trivial_single_record(rec)
    assert asm.provenance.source_record_ids() == (rec.source_record_id,)


def test_model_invariants_reject_inconsistent_construction(fixture_parquet: Path):
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    good = assemble_trivial_single_record(rec)
    # mismatched parallel tuples
    with pytest.raises(ValueError):
        SourceDocumentAssembly(
            provenance=good.provenance,
            member_source_record_ids=(rec.source_record_id,),
            member_roles=(),
            operations=(Operation.KEEP,),
            assembly_strategy=AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V1,
            assembly_status=AssemblyStatus.COMPLETE,
            assembled_text="x",
            assembled_text_hash=compute_assembled_text_hash("x"),
        )
    # complete + null text
    with pytest.raises(ValueError):
        SourceDocumentAssembly(
            provenance=good.provenance,
            member_source_record_ids=(rec.source_record_id,),
            member_roles=(MemberRole.PRIMARY,),
            operations=(Operation.KEEP,),
            assembly_strategy=AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V1,
            assembly_status=AssemblyStatus.COMPLETE,
            assembled_text=None,
            assembled_text_hash=None,
        )
    # inconsistent hash
    with pytest.raises(ValueError):
        SourceDocumentAssembly(
            provenance=good.provenance,
            member_source_record_ids=(rec.source_record_id,),
            member_roles=(MemberRole.PRIMARY,),
            operations=(Operation.KEEP,),
            assembly_strategy=AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V2,
            assembly_status=AssemblyStatus.COMPLETE,
            assembled_text="x",
            assembled_text_hash="sha256:wrong",
        )


def _assembly(rec, provenance, **overrides):
    fields = dict(
        provenance=provenance,
        member_source_record_ids=(rec.source_record_id,),
        member_roles=(MemberRole.PRIMARY,),
        operations=(Operation.KEEP,),
        assembly_strategy=AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V2,
        assembly_status=AssemblyStatus.COMPLETE,
        assembled_text="x",
        assembled_text_hash=compute_assembled_text_hash("x"),
    )
    fields.update(overrides)
    return SourceDocumentAssembly(**fields)


def test_members_must_match_provenance_inputs(fixture_parquet: Path):
    """P2: member ids that disagree with the provenance source-record inputs are rejected."""
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    good = assemble_trivial_single_record(rec)
    with pytest.raises(ValueError, match="exactly match the provenance"):
        _assembly(rec, good.provenance, member_source_record_ids=("srr:sha256:someone-else",))


def test_wrong_provenance_artifact_type_is_rejected(fixture_parquet: Path):
    """P2: an assembly whose provenance is not a SOURCE_DOCUMENT_ASSEMBLY node."""
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    wrong = DerivedArtifactProvenance.build(
        ArtifactType.QUALITY_ANNOTATION,
        source_record_inputs([rec.source_record_id]),
        "p",
        "1",
    )
    with pytest.raises(ValueError, match="artifact_type"):
        _assembly(rec, wrong)


def test_noncomposable_and_ambiguous_forbid_returnable_text(fixture_parquet: Path):
    """P2: the full status/text matrix — non-composable/ambiguous must have null text."""
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]
    good = assemble_trivial_single_record(rec)
    for status in (AssemblyStatus.NONCOMPOSABLE, AssemblyStatus.AMBIGUOUS):
        with pytest.raises(ValueError, match="null"):
            _assembly(
                rec,
                good.provenance,
                assembly_status=status,
                assembled_text="x",
                assembled_text_hash=compute_assembled_text_hash("x"),
            )
    # and a null-text partial is likewise rejected (partial must be returnable).
    with pytest.raises(ValueError, match="non-null"):
        _assembly(
            rec,
            good.provenance,
            assembly_status=AssemblyStatus.PARTIAL,
            assembled_text=None,
            assembled_text_hash=None,
        )
    # a null-text NONCOMPOSABLE is valid.
    ok = _assembly(
        rec,
        good.provenance,
        assembly_status=AssemblyStatus.NONCOMPOSABLE,
        assembled_text=None,
        assembled_text_hash=None,
    )
    assert ok.assembly_status == AssemblyStatus.NONCOMPOSABLE
