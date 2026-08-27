"""M1A.5 acceptance — the ``document_type``-based classification producer (review B2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from open_us_law_coverage.derived import AuthorityRole, DocumentClass, InputType
from open_us_law_coverage.derived.classification import (
    classify,
    classify_source_record,
    fr_default_off,
)
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT


class _Rec:
    """Minimal duck-typed stand-in: a source record exposes columns + an id."""

    source_record_id = "srr:test"

    def __init__(self, document_type, act_id):
        self._cols = {"document_type": document_type, "act_id": act_id}

    def column(self, name):
        return self._cols[name]


@pytest.mark.parametrize(
    "document_type, act_id, doc_class, role",
    [
        ("statute", "USC_T42_C21_S1983", DocumentClass.STATUTE, AuthorityRole.OPERATIVE_PRIMARY_LAW),
        ("statute", "STATE_CA_T1_S1", DocumentClass.STATUTE, AuthorityRole.OPERATIVE_PRIMARY_LAW),
        ("constitution", "SCONST_AK_A10_S0", DocumentClass.CONSTITUTION, AuthorityRole.OPERATIVE_PRIMARY_LAW),
        ("regulation", "CFR_T17_S240.10b-5", DocumentClass.CODIFIED_CFR, AuthorityRole.OPERATIVE_PRIMARY_LAW),
        ("regulation", "FR_2026_12345", DocumentClass.FEDERAL_REGISTER, AuthorityRole.PROMULGATION_RECORD),
        ("court_rule", "SRULES_AK_1", DocumentClass.COURT_RULE, AuthorityRole.OPERATIVE_PRIMARY_LAW),
        ("guidance", "JM_9_1", DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
        ("ruling", "SSA_2026_1", DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
        ("irs_notice", "IRS_2026_1", DocumentClass.GUIDANCE, AuthorityRole.GUIDANCE),
    ],
)
def test_document_type_broad_class(document_type, act_id, doc_class, role):
    got_class, got_role, confidence, _ = classify(document_type, act_id)
    assert (got_class, got_role) == (doc_class, role)
    assert confidence == 1.0


def test_state_prefix_splits_statute_and_regulation():
    """The headline B2 bug: ``STATE_*`` collapses statutes and regulations. The
    document_type column, not the prefix, is what keeps them apart."""
    stat_class, *_ = classify("statute", "STATE_CA_T1_S1")
    reg_class, reg_role, reg_conf, _ = classify("regulation", "STATE_CO_R1")
    assert stat_class == DocumentClass.STATUTE
    assert reg_class == DocumentClass.REGULATION  # NOT statute
    assert reg_role == AuthorityRole.OPERATIVE_PRIMARY_LAW
    assert reg_conf == 1.0


def test_court_rule_and_guidance_are_reachable():
    assert classify("court_rule", "SRULES_AK_1")[0] == DocumentClass.COURT_RULE
    assert classify("court_rule", "FRULES_1")[0] == DocumentClass.COURT_RULE
    assert classify("guidance", "NY_1")[0] == DocumentClass.GUIDANCE


@pytest.mark.parametrize(
    "document_type, act_id",
    [
        (None, "USC_T1_S1"),
        ("", "USC_T1_S1"),
        ("executive_order", "EXEC_1"),   # recognized type, no broad-class home
        ("treaty", "TREATY_1"),
        ("mystery_type", "STATE_CA_T1_S1"),
    ],
)
def test_unmapped_document_type_abstains(document_type, act_id):
    doc_class, role, confidence, evidence = classify(document_type, act_id)
    assert doc_class == DocumentClass.UNKNOWN
    assert role == AuthorityRole.UNKNOWN
    assert confidence == 0.0
    assert evidence  # keeps a reason


@pytest.mark.parametrize(
    "document_type, act_id",
    [
        ("regulation", "USC_T42_S1"),   # USC namespace expects statute
        ("statute", "CFR_T17_S1"),      # CFR namespace expects regulation
        ("statute", "SCONST_AK_A1"),    # SCONST expects constitution
        ("regulation", "SRULES_1"),     # SRULES expects court_rule
    ],
)
def test_prefix_type_conflict_abstains_and_keeps_both_signals(document_type, act_id):
    doc_class, role, confidence, evidence = classify(document_type, act_id)
    assert doc_class == DocumentClass.UNKNOWN
    assert confidence == 0.0
    kinds = {e.kind for e in evidence}
    assert {"document_type", "act_id_prefix"} <= kinds  # both signals retained


def test_state_prefix_never_conflicts():
    """``STATE_*`` is genuinely ambiguous, so it must not trigger the conflict path
    for either statutes or regulations."""
    assert classify("statute", "STATE_CA_1")[0] == DocumentClass.STATUTE
    assert classify("regulation", "STATE_CA_1")[0] == DocumentClass.REGULATION


def test_fr_default_off_only_for_federal_register():
    ann = classify_source_record(_Rec("regulation", "FR_2026_1"))
    assert ann.document_class == DocumentClass.FEDERAL_REGISTER
    assert fr_default_off(ann) is True

    cfr = classify_source_record(_Rec("regulation", "CFR_T17_S1"))
    assert cfr.document_class == DocumentClass.CODIFIED_CFR
    assert fr_default_off(cfr) is False


def test_provenance_anchors_to_source_record_id(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    for rec in records:
        ann = classify_source_record(rec)
        assert ann.provenance.source_record_ids() == (rec.source_record_id,)
        assert all(e.input_type == InputType.SOURCE_RECORD for e in ann.provenance.inputs)


def test_real_fixture_all_classified(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    classes = {classify_source_record(r).document_class for r in records}
    # the fixture carries statute + constitution document_types
    assert DocumentClass.STATUTE in classes
    assert DocumentClass.CONSTITUTION in classes
    assert DocumentClass.UNKNOWN not in classes


def test_prefix_evidence_is_truthful():
    """Review P3: the prefix evidence is only confident when the prefix actually
    contributed. A non-refining/ambiguous prefix (STATE) must not claim confidence."""
    # STATE contributed nothing (document_type alone set the class).
    _, _, _, ev = classify("statute", "STATE_CA_1")
    prefix_ev = next(e for e in ev if e.kind == "act_id_prefix")
    assert prefix_ev.confidence is None
    assert "non-refining" in prefix_ev.detail

    _, _, _, ev = classify("regulation", "STATE_CO_1")
    prefix_ev = next(e for e in ev if e.kind == "act_id_prefix")
    assert prefix_ev.confidence is None

    # CFR/FR genuinely refine -> confident prefix evidence.
    _, _, _, ev = classify("regulation", "CFR_T17_S1")
    prefix_ev = next(e for e in ev if e.kind == "act_id_prefix")
    assert prefix_ev.confidence == 1.0
    assert "refines" in prefix_ev.detail

    # USC confirms a fixed expectation -> confident prefix evidence.
    _, _, _, ev = classify("statute", "USC_T1_S1")
    prefix_ev = next(e for e in ev if e.kind == "act_id_prefix")
    assert prefix_ev.confidence == 1.0
    assert "confirms" in prefix_ev.detail

    # document_type always carries the confidence regardless.
    dt_ev = next(e for e in ev if e.kind == "document_type")
    assert dt_ev.confidence == 1.0


def _assert_no_high_confidence_contradiction(document_type, act_id):
    from open_us_law_coverage.derived.classification import (
        _PREFIX_EXPECTED_CLASS,
        act_id_prefix,
    )

    _REFINED = {DocumentClass.CODIFIED_CFR, DocumentClass.FEDERAL_REGISTER}
    doc_class, _role, confidence, _ev = classify(document_type, act_id)
    if confidence < 1.0:
        return
    expected = _PREFIX_EXPECTED_CLASS.get(act_id_prefix(act_id))
    if expected is None:
        return
    broad = DocumentClass.REGULATION if doc_class in _REFINED else doc_class
    assert broad == expected, (act_id, doc_class)


def test_ak_constitutions_sample_no_high_confidence_contradictions(real_sample_parquet: Path):
    """Guard over the committed AK-constitutions sample (not the whole snapshot):
    no confidently-classified record contradicts its ``act_id`` namespace expectation."""
    for rec in read_source_records(real_sample_parquet, SNAPSHOT):
        _assert_no_high_confidence_contradiction(rec.column("document_type"), rec.column("act_id"))


def test_full_snapshot_no_high_confidence_contradictions():
    """Optional full-snapshot regression (review P3). Scans only the small
    ``act_id``/``document_type`` columns (never ``text``), so it is OOM-safe; skips
    when the full snapshot is not present."""
    import glob

    import pyarrow.parquet as pq

    files = sorted(glob.glob("data/v2026.08_full/*.parquet"))
    if not files:
        pytest.skip("full snapshot data/v2026.08_full/ not present")
    for path in files:
        pf = pq.ParquetFile(path)
        for batch in pf.iter_batches(columns=["act_id", "document_type"], batch_size=200_000):
            act_ids = batch.column("act_id").to_pylist()
            dts = batch.column("document_type").to_pylist()
            for act_id, dt in zip(act_ids, dts):
                _assert_no_high_confidence_contradiction(dt, act_id)
