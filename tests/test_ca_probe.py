"""M0.5B3 acceptance — the falsification probe mechanics.

Run on the hermetic fixture (whose two byte-identical rows carry *distinct*
``act_id``s) to test the content-vs-identity distinction the CA probe exists to
surface, plus an opt-in pass on the committed real CA sample.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from open_us_law_coverage.ca_probe import analyze_ca

_REAL_CA = Path("data/v2026.08/us_ca_statutes.parquet")


def test_content_dup_across_distinct_identities(fixture_parquet: Path):
    res = analyze_ca(fixture_parquet)
    # the fixture's byte-identical twins have different act_ids -> one shared hash
    # spanning two rows, which is content duplication, NOT identity duplication.
    assert res.content_dup_hashes == 1
    assert res.content_dup_rows == 2
    assert res.content_dup_example is not None
    assert len(set(res.content_dup_example)) == 2  # two DISTINCT provisions


def test_identity_and_paths_stay_distinct_despite_shared_text(fixture_parquet: Path):
    res = analyze_ca(fixture_parquet)
    # every row is its own provision: act_ids and structural paths are 1:1.
    assert res.distinct_act_ids == res.rows
    # rows with a parseable breadcrumb all get a distinct structural path
    assert res.distinct_structural_paths == res.parse_ok


def test_assembly_is_lossless(fixture_parquet: Path):
    res = analyze_ca(fixture_parquet)
    assert res.assembly_lossless is True
    assert res.assembly_checked == res.rows  # full corpus, not sampled


def test_identity_producer_and_within_group_dedup(fixture_parquet: Path):
    """The real identity producer runs per row (single-member groups), and
    detect_duplicate_rows within each group flags nothing — even though the fixture's
    byte-identical twins are content duplicates across distinct identities."""
    res = analyze_ca(fixture_parquet)
    assert res.identity_single_member == res.rows
    assert res.identity_multi_member == 0
    assert res.within_group_duplicate_rows == 0
    # content duplication still exists at corpus scope (the contrast).
    assert res.content_dup_rows == 2


def test_no_distortion_on_real_ca_sample():
    if not _REAL_CA.exists():
        pytest.skip(f"gated sample {_REAL_CA} not present")
    res = analyze_ca(_REAL_CA)
    assert res.rows > 0
    assert res.parse_fail == 0                       # breadcrumb parses everywhere
    assert res.distinct_act_ids == res.rows          # identity 1:1
    assert res.distinct_structural_paths == res.rows # structural anchor 1:1
    assert res.assembly_lossless is True
    assert res.assembly_checked == res.rows          # full corpus
    assert set(res.doc_class) == {"statute"}
    # real identity producer: every row a single-member group; 0 within-group dups.
    assert res.identity_single_member == res.rows
    assert res.identity_multi_member == 0
    assert res.within_group_duplicate_rows == 0
    assert set(res.identity_strategy) == {"state_statute_act_id_v1"}
