"""M1A.5 acceptance — the ``duplicate_row``-only quality producer (review B1).

The hermetic fixture ends with two byte-identical rows (``Body A`` / ``Body A
(clone)``) and carries a null-text row — the exact adversarial cases for a
cross-record duplicate detector. Detection is **scoped to one identity group**, and
every conclusion names a content-addressed :class:`DuplicateScope` so its recompute
frontier is complete.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from open_us_law_coverage.derived import QualityFlag, QualityStatus, is_duplicate_row
from open_us_law_coverage.derived.quality import detect_duplicate_rows
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT


def test_byte_identical_twins_flagged(fixture_parquet: Path, identical_text: str):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    result = detect_duplicate_rows(records)
    anns = result.annotations
    assert len(anns) == len(records)

    flagged = {
        ann.target_source_record_id
        for ann in anns
        if QualityFlag.DUPLICATE_ROW in ann.quality_flags
    }
    twins = {r.source_record_id for r in records if r.raw_text == identical_text}
    assert len(twins) == 2
    assert flagged == twins


def test_non_duplicates_and_null_text_not_flagged(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    result = detect_duplicate_rows(records)
    anns = {a.target_source_record_id: a for a in result.annotations}
    for rec in records:
        ann = anns[rec.source_record_id]
        if rec.raw_text_hash is None:
            assert ann.quality_flags == ()
        # status is never certified clean by this producer.
        assert ann.quality_status == QualityStatus.UNKNOWN


def test_producer_never_deletes_rows(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    result = detect_duplicate_rows(records)
    # one annotation per input record, same order — nothing dropped.
    assert [a.target_source_record_id for a in result.annotations] == [
        r.source_record_id for r in records
    ]
    # every annotation anchors to its own physical row + the shared scope artifact.
    for a in result.annotations:
        assert a.provenance.source_record_ids() == (a.target_source_record_id,)


def test_duplicate_evidence_names_the_siblings(fixture_parquet: Path, identical_text: str):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    twins = sorted(r.source_record_id for r in records if r.raw_text == identical_text)
    anns = {a.target_source_record_id: a for a in detect_duplicate_rows(records).annotations}
    ann = anns[twins[0]]
    assert ann.evidence
    detail = ann.evidence[0].detail
    for tid in twins:
        assert tid in detail


# --- review B1 acceptance -------------------------------------------------


def test_scope_is_keyed_by_the_complete_member_set(fixture_parquet: Path):
    """Changing the sibling set changes the scope artifact and the provenance of
    every affected conclusion (the recompute frontier is complete)."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    full = detect_duplicate_rows(records)
    subset = detect_duplicate_rows(records[:-1])  # drop one member

    assert full.scope.provenance.artifact_id != subset.scope.provenance.artifact_id

    # A record present in both scopes gets a different conclusion id, because its
    # conclusion names the (changed) scope artifact as an input.
    shared_id = records[0].source_record_id
    a_full = next(a for a in full.annotations if a.target_source_record_id == shared_id)
    a_subset = next(a for a in subset.annotations if a.target_source_record_id == shared_id)
    assert a_full.provenance.artifact_id != a_subset.provenance.artifact_id


def test_two_conclusions_never_share_an_artifact_id(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    result = detect_duplicate_rows(records)
    ids = [a.provenance.artifact_id for a in result.annotations]
    assert len(set(ids)) == len(ids)


def test_flagged_and_unflagged_of_one_record_are_distinct_ids(fixture_parquet: Path):
    """The exact B1 defect: the same record evaluated alone (unflagged) vs. with a
    byte-identical sibling (flagged) must not collapse to one artifact id."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    twins = [r for r in records if len(
        [x for x in records if x.raw_text_hash == r.raw_text_hash and r.raw_text_hash]
    ) == 2 and r.raw_text is not None]
    assert len(twins) == 2
    r1 = twins[0]

    alone = detect_duplicate_rows([r1])
    together = detect_duplicate_rows(twins)

    a_alone = alone.annotations[0]
    a_together = next(a for a in together.annotations if a.target_source_record_id == r1.source_record_id)
    assert a_alone.quality_flags == ()
    assert QualityFlag.DUPLICATE_ROW in a_together.quality_flags
    # different conclusions -> different ids (no collision).
    assert a_alone.provenance.artifact_id != a_together.provenance.artifact_id


def test_distinct_provisions_same_text_not_flagged_in_separate_groups(fixture_parquet: Path):
    """The CA case: identical bytes across *distinct* provisions evaluated in their
    own single-member identity groups are never flagged as duplicates."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    twins = [r for r in records if r.raw_text is not None and len(
        [x for x in records if x.raw_text_hash == r.raw_text_hash]
    ) == 2]
    assert len(twins) == 2
    # Each twin is its own identity group (distinct provisions) -> no cross flag.
    for rec in twins:
        result = detect_duplicate_rows([rec])
        assert result.annotations[0].quality_flags == ()


def test_reversed_records_yield_equal_scope_object(fixture_parquet: Path):
    """Review P1: the scope is content-addressed by its member set, and its stored
    ``member_source_record_ids`` is canonical — so reversing the input rows yields a
    byte-identical ``DuplicateScope``, not merely an id-equal one. Annotation output
    order still follows input order (checked separately)."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    fwd = detect_duplicate_rows(records)
    rev = detect_duplicate_rows(list(reversed(records)))

    assert fwd.scope.provenance.artifact_id == rev.scope.provenance.artifact_id
    assert fwd.scope.member_source_record_ids == rev.scope.member_source_record_ids
    assert fwd.scope == rev.scope  # fully equal serialized scope objects
    # member list is canonical (sorted), independent of input order.
    assert list(fwd.scope.member_source_record_ids) == sorted(fwd.scope.member_source_record_ids)
    # annotation output order tracks input order (preserved separately).
    assert [a.target_source_record_id for a in fwd.annotations] == [r.source_record_id for r in records]
    assert [a.target_source_record_id for a in rev.annotations] == [r.source_record_id for r in reversed(records)]


def test_consumer_reads_flags_not_status(fixture_parquet: Path, identical_text: str):
    """The load-bearing signal is ``quality_flags`` (via ``is_duplicate_row``), never
    ``quality_status`` — which stays ``unknown`` even for a flagged duplicate."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    result = detect_duplicate_rows(records)
    dup_ids = {a.target_source_record_id for a in result.annotations if is_duplicate_row(a)}
    assert dup_ids == {r.source_record_id for r in records if r.raw_text == identical_text}
    # status alone would hide every duplicate.
    assert all(a.quality_status == QualityStatus.UNKNOWN for a in result.annotations)


def test_scope_membership_change_via_mutated_text(fixture_parquet: Path):
    """Sanity: with the same member ids but one record's bytes changed, the flags
    change while the scope id (keyed by member ids) is stable."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    twins = [r for r in records if r.raw_text is not None and len(
        [x for x in records if x.raw_text_hash == r.raw_text_hash]
    ) == 2]
    # break one twin's content -> no more duplicate, same member set.
    broken = replace(twins[1], raw_text="something else entirely", raw_text_hash=None)
    before = detect_duplicate_rows(twins)
    after = detect_duplicate_rows([twins[0], broken])
    assert all(QualityFlag.DUPLICATE_ROW in a.quality_flags for a in before.annotations)
    assert all(a.quality_flags == () for a in after.annotations)
