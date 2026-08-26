"""M1A.5 acceptance — the ``duplicate_row``-only quality producer.

The hermetic fixture ends with two byte-identical rows (``Body A`` / ``Body A
(clone)``) and carries a null-text row — the exact adversarial cases for a
cross-record duplicate detector.
"""

from __future__ import annotations

from pathlib import Path

from open_us_law_coverage.derived import QualityFlag, QualityStatus
from open_us_law_coverage.derived.quality import detect_duplicate_rows
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT


def _by_id(records):
    return {r.source_record_id: r for r in records}


def test_byte_identical_twins_flagged(fixture_parquet: Path, identical_text: str):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    anns = detect_duplicate_rows(records)
    assert len(anns) == len(records)

    flagged = {
        rec.source_record_id
        for rec, ann in zip(records, anns)
        if QualityFlag.DUPLICATE_ROW in ann.quality_flags
    }
    twins = {r.source_record_id for r in records if r.raw_text == identical_text}
    assert len(twins) == 2
    assert flagged == twins


def test_non_duplicates_and_null_text_not_flagged(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    anns = dict(zip((r.source_record_id for r in records), detect_duplicate_rows(records)))
    for rec in records:
        ann = anns[rec.source_record_id]
        # the null-text row and the empty-string row are unique -> no flag.
        if rec.raw_text_hash is None:
            assert ann.quality_flags == ()
        # status is never certified clean by this producer.
        assert ann.quality_status == QualityStatus.UNKNOWN


def test_producer_never_deletes_rows(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    anns = detect_duplicate_rows(records)
    # one annotation per input record, same order — nothing dropped.
    assert [a.provenance.source_record_ids()[0] for a in anns] == [
        r.source_record_id for r in records
    ]


def test_duplicate_evidence_names_the_siblings(fixture_parquet: Path, identical_text: str):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    twins = sorted(r.source_record_id for r in records if r.raw_text == identical_text)
    anns = dict(zip((r.source_record_id for r in records), detect_duplicate_rows(records)))
    ann = anns[twins[0]]
    assert ann.evidence
    detail = ann.evidence[0].detail
    for tid in twins:
        assert tid in detail
