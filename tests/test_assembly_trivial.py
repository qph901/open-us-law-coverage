"""M1A.5 acceptance — the ``trivial_single_record_v1`` assembly producer."""

from __future__ import annotations

from pathlib import Path

from open_us_law_coverage.derived import (
    AssemblyStatus,
    AssemblyStrategy,
    MemberRole,
    Operation,
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
        asm = assemble_trivial_single_record(rec, source_identity_key="KEY")
        # not one byte invented or dropped; null stays null.
        assert asm.assembled_text == rec.raw_text
        assert asm.assembled_text_hash == compute_assembled_text_hash(rec.raw_text)
        assert asm.assembly_strategy == AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V1
        assert asm.assembly_status == AssemblyStatus.COMPLETE
        assert asm.operations == (Operation.KEEP,)
        assert asm.member_roles == (MemberRole.PRIMARY,)
        assert asm.member_source_record_ids == (rec.source_record_id,)


def test_null_text_stays_null(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    null_recs = [r for r in records if r.raw_text is None]
    assert null_recs  # the fixture has one
    for rec in null_recs:
        asm = assemble_trivial_single_record(rec, source_identity_key="KEY")
        assert asm.assembled_text is None
        assert asm.assembled_text_hash is None


def test_assembly_provenance_anchors_to_source_record(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    rec = records[0]
    asm = assemble_trivial_single_record(rec, source_identity_key="KEY")
    assert asm.provenance.source_record_ids() == (rec.source_record_id,)
