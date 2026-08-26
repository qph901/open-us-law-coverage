"""M1A.5 acceptance — the deterministic ``DocumentClassificationAnnotation`` producer."""

from __future__ import annotations

from pathlib import Path

import pytest

from open_us_law_coverage.derived import AuthorityRole, DocumentClass, InputType
from open_us_law_coverage.derived.classification import (
    classify_act_id,
    classify_source_record,
    fr_default_off,
)
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT


@pytest.mark.parametrize(
    "act_id, doc_class, role",
    [
        ("USC_T42_C21_S1983", DocumentClass.STATUTE, AuthorityRole.OPERATIVE_PRIMARY_LAW),
        ("STATE_AK_T10_C10.06_S10.06.005", DocumentClass.STATUTE, AuthorityRole.OPERATIVE_PRIMARY_LAW),
        ("SCONST_AK_A10_S0", DocumentClass.CONSTITUTION, AuthorityRole.OPERATIVE_PRIMARY_LAW),
        ("CFR_T17_S240.10b-5", DocumentClass.CODIFIED_CFR, AuthorityRole.OPERATIVE_PRIMARY_LAW),
        ("FR_2026_12345", DocumentClass.FEDERAL_REGISTER, AuthorityRole.PROMULGATION_RECORD),
    ],
)
def test_prefix_mapping(act_id, doc_class, role):
    got_class, got_role, confidence, _ = classify_act_id(act_id)
    assert (got_class, got_role) == (doc_class, role)
    assert confidence == 1.0


@pytest.mark.parametrize("act_id", [None, "", "MYSTERY_T1_S1", "randomtext"])
def test_unrecognized_prefix_abstains(act_id):
    doc_class, role, confidence, _ = classify_act_id(act_id)
    assert doc_class == DocumentClass.UNKNOWN
    assert role == AuthorityRole.UNKNOWN
    assert confidence == 0.0


def test_fr_default_off_only_for_federal_register():
    class _Rec:
        source_record_id = "srr:test"

        def column(self, name):
            return {"act_id": "FR_2026_1"}[name]

    ann = classify_source_record(_Rec())
    assert ann.document_class == DocumentClass.FEDERAL_REGISTER
    assert fr_default_off(ann) is True

    class _Cfr(_Rec):
        def column(self, name):
            return {"act_id": "CFR_T17_S1"}[name]

    assert fr_default_off(classify_source_record(_Cfr())) is False


def test_provenance_anchors_to_source_record_id(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    for rec in records:
        ann = classify_source_record(rec)
        # every provenance edge is a source_record edge, and it is *this* record.
        assert ann.provenance.source_record_ids() == (rec.source_record_id,)
        assert all(e.input_type == InputType.SOURCE_RECORD for e in ann.provenance.inputs)


def test_real_fixture_all_classified(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    classes = {classify_source_record(r).document_class for r in records}
    # the fixture carries USC, STATE, and SCONST act_ids
    assert DocumentClass.STATUTE in classes
    assert DocumentClass.CONSTITUTION in classes
    assert DocumentClass.UNKNOWN not in classes
