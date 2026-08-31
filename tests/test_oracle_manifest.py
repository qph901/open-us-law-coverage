from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from open_us_law_coverage.derived import InputType
from open_us_law_coverage.oracle_manifest import CutoffStatus, load_oracle_manifest

MANIFEST = Path("oracles/v2026.08.json")


def test_v202608_currency_registry_uses_corpus_evidence_not_commit_date():
    manifest = load_oracle_manifest(MANIFEST)
    assert manifest.snapshot == "v2026.08"
    assert manifest.repository_commit_date_is_content_cutoff is False
    corpora = {corpus.corpus: corpus for corpus in manifest.corpora}
    assert set(corpora) == {"us_federal_statutes", "us_federal_regulations"}

    statutes = corpora["us_federal_statutes"]
    assert statutes.cutoff_status == CutoffStatus.ESTABLISHED
    assert statutes.snapshot_content_cutoff == "2025-01-06"
    assert statutes.residual_skew_days == 0
    assert "USCODE-2024" in statutes.basis

    regulations = corpora["us_federal_regulations"]
    assert regulations.cutoff_status == CutoffStatus.UNRESOLVED
    assert regulations.snapshot_content_cutoff is None
    assert regulations.residual_skew_days is None
    assert "moving /current/ eCFR URLs" in regulations.basis


def test_oracle_candidates_have_stable_provenance_ids_but_are_visibly_unstaged():
    manifest = load_oracle_manifest(MANIFEST)
    assert {edition.kind for edition in manifest.editions}
    for edition in manifest.editions:
        assert edition.staged is False
        assert edition.provenance_input().input_type == InputType.ORACLE_EDITION
        assert edition.provenance_input().input_id == edition.oracle_edition


def test_registry_rejects_publication_date_as_legal_content_cutoff():
    manifest = load_oracle_manifest(MANIFEST)
    with pytest.raises(ValueError, match="publication metadata"):
        replace(manifest, repository_commit_date_is_content_cutoff=True)
