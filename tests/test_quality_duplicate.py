"""Acceptance tests for identity-bound ``duplicate_row`` detection."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from open_us_law_coverage.derived import (
    ArtifactType,
    DerivedArtifactProvenance,
    IdentityMember,
    IdentityScope,
    IdentityStatus,
    InputType,
    QualityFlag,
    QualityStatus,
    SourceIdentityGroup,
    cfr_identity_group,
    detect_duplicate_rows,
    is_duplicate_row,
    source_record_inputs,
)
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _member(rid: str, ordinal: int, text: str | None) -> IdentityMember:
    return IdentityMember(
        source_record_id=rid,
        act_id="CFR_T17_P240_S240.10b-5",
        state="US",
        corpus="regulations",
        document_type="regulation",
        raw_text_hash=None if text is None else _hash(text),
        physical_row_ordinal=ordinal,
    )


def _group(records: list[IdentityMember]):
    return cfr_identity_group(records).group


def test_byte_identical_twins_flagged_only_within_their_identity_group():
    records = [
        _member("r1", 1, "same"),
        _member("r2", 2, "same"),
        _member("r3", 3, "different"),
        _member("r4", 4, None),
    ]
    result = detect_duplicate_rows(_group(records), records)
    flagged = {
        ann.target_source_record_id
        for ann in result.annotations
        if QualityFlag.DUPLICATE_ROW in ann.quality_flags
    }
    assert flagged == {"r1", "r2"}
    assert all(a.quality_status == QualityStatus.UNKNOWN for a in result.annotations)


def test_duplicate_evidence_names_the_siblings():
    records = [_member("r1", 1, "same"), _member("r2", 2, "same")]
    anns = {
        a.target_source_record_id: a
        for a in detect_duplicate_rows(_group(records), records).annotations
    }
    for rid in ("r1", "r2"):
        assert rid in anns["r1"].evidence[0].detail


def test_scope_is_bound_to_identity_group_and_complete_member_set():
    records = [_member("r1", 1, "a"), _member("r2", 2, "b")]
    group = _group(records)
    result = detect_duplicate_rows(group, records)

    assert result.scope.identity_group_artifact_id == group.provenance.artifact_id
    assert result.scope.provenance.input_ids_of(InputType.ANNOTATION) == (
        group.provenance.artifact_id,
    )
    assert result.scope.provenance.source_record_ids() == ("r1", "r2")


@pytest.mark.parametrize(
    "records",
    [
        [_member("r1", 1, "a")],
        [_member("r1", 1, "a"), _member("r1", 1, "a")],
        [_member("r1", 1, "a"), _member("r3", 3, "c")],
    ],
    ids=["missing-member", "duplicate-record", "foreign-member"],
)
def test_detector_rejects_records_that_are_not_exactly_the_group(records):
    expected = [_member("r1", 1, "a"), _member("r2", 2, "b")]
    with pytest.raises(ValueError):
        detect_duplicate_rows(_group(expected), records)


def test_membership_change_rehashes_scope_and_surviving_annotations():
    full_records = [
        _member("r1", 1, "same"),
        _member("r2", 2, "same"),
        _member("r3", 3, "other"),
    ]
    subset_records = full_records[:2]
    full = detect_duplicate_rows(_group(full_records), full_records)
    subset = detect_duplicate_rows(_group(subset_records), subset_records)

    assert full.scope.provenance.artifact_id != subset.scope.provenance.artifact_id
    full_ids = {
        a.target_source_record_id: a.provenance.artifact_id for a in full.annotations
    }
    subset_ids = {
        a.target_source_record_id: a.provenance.artifact_id for a in subset.annotations
    }
    for rid in subset_ids:
        assert full_ids[rid] != subset_ids[rid]


def test_same_record_flagged_and_unflagged_has_distinct_ids():
    pair = [_member("r1", 1, "same"), _member("r2", 2, "same")]
    alone = detect_duplicate_rows(_group(pair[:1]), pair[:1])
    together = detect_duplicate_rows(_group(pair), pair)

    assert alone.annotations[0].quality_flags == ()
    pair_ann = next(a for a in together.annotations if a.target_source_record_id == "r1")
    assert is_duplicate_row(pair_ann)
    assert alone.annotations[0].provenance.artifact_id != pair_ann.provenance.artifact_id


def test_reversed_records_yield_equal_scope_and_preserve_annotation_order():
    records = [_member("r1", 1, "a"), _member("r2", 2, "b")]
    group = _group(records)
    fwd = detect_duplicate_rows(group, records)
    rev = detect_duplicate_rows(group, list(reversed(records)))

    assert fwd.scope == rev.scope
    assert [a.target_source_record_id for a in fwd.annotations] == ["r1", "r2"]
    assert [a.target_source_record_id for a in rev.annotations] == ["r2", "r1"]


def test_same_member_ids_with_changed_content_changes_flags_not_scope():
    records = [_member("r1", 1, "same"), _member("r2", 2, "same")]
    group = _group(records)
    changed = [records[0], replace(records[1], raw_text_hash=_hash("changed"))]

    before = detect_duplicate_rows(group, records)
    after = detect_duplicate_rows(group, changed)
    assert before.scope == after.scope
    assert all(is_duplicate_row(a) for a in before.annotations)
    assert all(not is_duplicate_row(a) for a in after.annotations)


def test_distinct_provisions_same_text_are_not_cross_flagged(
    fixture_parquet: Path, identical_text: str
):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    twins = [r for r in records if r.raw_text == identical_text]
    assert len(twins) == 2

    for record in twins:
        provenance = DerivedArtifactProvenance.build(
            ArtifactType.SOURCE_IDENTITY_GROUP,
            source_record_inputs([record.source_record_id]),
            "test_identity",
            "1",
        )
        group = SourceIdentityGroup(
            provenance=provenance,
            strategy_name="test_identity",
            source_identity_key=f"fixture|{record.column('act_id')}",
            member_source_record_ids=(record.source_record_id,),
            identity_scope=IdentityScope.DOCUMENT,
            identity_status=IdentityStatus.RESOLVED,
            confidence=1.0,
        )
        result = detect_duplicate_rows(group, [record])
        assert result.annotations[0].quality_flags == ()


def test_producer_never_drops_group_members():
    records = [_member("r1", 1, "a"), _member("r2", 2, "a")]
    result = detect_duplicate_rows(_group(records), records)
    assert [a.target_source_record_id for a in result.annotations] == ["r1", "r2"]
    assert len({a.provenance.artifact_id for a in result.annotations}) == 2
