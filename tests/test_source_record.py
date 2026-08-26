"""M1A acceptance suite — golden-fixture invariants for the immutable core.

Exit criteria from ``PROPOSAL.md`` M1A, each mapped to a test below:

* no text lost                                   -> test_no_text_lost
* every column verbatim; null stays null         -> test_columns_verbatim,
                                                    test_null_stays_null,
                                                    test_no_invented_columns
* source_record_id deterministic from
  (snapshot, file checksum, physical ordinal)    -> test_source_record_id_formula,
                                                    test_read_is_deterministic,
                                                    test_ordinals_contiguous_across_row_groups
* raw_text[start:end] resolves for stored offsets-> test_offsets_resolve,
                                                    test_offsets_resolve_unicode
* boundary test: a simulated parser improvement
  requires ZERO changes to any source record     -> test_boundary_parser_improvement,
                                                    test_record_is_immutable,
                                                    test_original_columns_is_read_only

Plus supporting invariants on the content hash and file checksum.
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from open_us_law_coverage.source_record import (
    EXPECTED_COLUMNS,
    METADATA_COLUMNS,
    CanonicalSourceRecord,
    compute_raw_text_hash,
    compute_source_record_id,
    file_sha256,
    iter_source_records,
    read_source_records,
)
from tests.conftest import SNAPSHOT


# ---------------------------------------------------------------------------
# Losslessness: text and columns preserved verbatim.
# ---------------------------------------------------------------------------

def test_no_text_lost(fixture_parquet: Path, fixture_rows, text_column_name):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    assert len(records) == len(fixture_rows)
    for record, row in zip(records, fixture_rows):
        assert record.raw_text == row[text_column_name]


def test_columns_verbatim(fixture_parquet: Path, fixture_rows):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    for record, row in zip(records, fixture_rows):
        for name in METADATA_COLUMNS:
            assert record.column(name) == row[name], name


def test_null_stays_null(fixture_parquet: Path, fixture_rows):
    """Null cells stay ``None`` — never coerced to "", 0, or invented."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    for record, row in zip(records, fixture_rows):
        for name in METADATA_COLUMNS:
            if row[name] is None:
                assert record.column(name) is None, name
        # Null text stays None; empty-string text stays "" (distinct).
        if row["text"] is None:
            assert record.raw_text is None
        else:
            assert record.raw_text == row["text"]


def test_empty_string_text_is_not_null(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    empties = [r for r in records if r.raw_text == ""]
    nulls = [r for r in records if r.raw_text is None]
    assert empties and nulls
    # Empty string is content (hashable); null is absence (no hash).
    assert empties[0].raw_text_hash == compute_raw_text_hash("")
    assert nulls[0].raw_text_hash is None


def test_no_invented_columns(fixture_parquet: Path):
    """``original_columns`` holds exactly the 23 metadata columns — no more."""
    record = read_source_records(fixture_parquet, SNAPSHOT)[0]
    assert set(record.original_columns) == set(METADATA_COLUMNS)
    assert "text" not in record.original_columns  # held once as raw_text


# ---------------------------------------------------------------------------
# Identity: source_record_id derives from physical coordinates only.
# ---------------------------------------------------------------------------

def test_source_record_id_formula(fixture_parquet: Path):
    checksum = file_sha256(fixture_parquet)
    records = read_source_records(fixture_parquet, SNAPSHOT)
    for record in records:
        assert record.source_file_checksum == checksum
        expected = compute_source_record_id(
            SNAPSHOT, checksum, record.physical_row_ordinal
        )
        assert record.source_record_id == expected


def test_source_record_id_ignores_content_and_snapshot():
    """Same physical coordinates -> same id; a different snapshot or checksum or
    ordinal -> different id. Content never enters the id."""
    base = compute_source_record_id("v2026.08", "abc", 0)
    assert base == compute_source_record_id("v2026.08", "abc", 0)
    assert base != compute_source_record_id("v2026.09", "abc", 0)
    assert base != compute_source_record_id("v2026.08", "abd", 0)
    assert base != compute_source_record_id("v2026.08", "abc", 1)


def test_read_is_deterministic(fixture_parquet: Path):
    """Two independent reads yield identical records field-for-field."""
    a = read_source_records(fixture_parquet, SNAPSHOT)
    b = read_source_records(fixture_parquet, SNAPSHOT)
    assert [_fingerprint(r) for r in a] == [_fingerprint(r) for r in b]


def test_ordinals_contiguous_across_row_groups(fixture_parquet: Path, fixture_rows):
    """The fixture spans multiple row groups; ordinals must be 0..n-1 in
    physical order regardless of row-group boundaries."""
    assert pq.ParquetFile(fixture_parquet).num_row_groups > 1
    records = read_source_records(fixture_parquet, SNAPSHOT)
    assert [r.physical_row_ordinal for r in records] == list(range(len(fixture_rows)))
    # Physical order preserved: citations come back in the authored order.
    assert [r.column("citation") for r in records] == [
        row["citation"] for row in fixture_rows
    ]


def test_iter_matches_read(fixture_parquet: Path):
    streamed = list(iter_source_records(fixture_parquet, SNAPSHOT))
    eager = read_source_records(fixture_parquet, SNAPSHOT)
    assert [_fingerprint(r) for r in streamed] == [_fingerprint(r) for r in eager]


# ---------------------------------------------------------------------------
# Content hash: over raw bytes; equal content -> equal hash, distinct id.
# ---------------------------------------------------------------------------

def test_raw_text_hash_over_raw_bytes(fixture_parquet: Path):
    for record in read_source_records(fixture_parquet, SNAPSHOT):
        if record.raw_text is None:
            assert record.raw_text_hash is None
        else:
            digest = hashlib.sha256(record.raw_text.encode("utf-8")).hexdigest()
            assert record.raw_text_hash == "sha256:" + digest


def test_identical_text_shares_hash_but_not_id(fixture_parquet: Path, identical_text):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    twins = [r for r in records if r.raw_text == identical_text]
    assert len(twins) == 2
    # Content-addressed: identical bytes -> identical hash ...
    assert twins[0].raw_text_hash == twins[1].raw_text_hash
    # ... but they are distinct physical rows -> distinct ids.
    assert twins[0].source_record_id != twins[1].source_record_id
    assert twins[0].physical_row_ordinal != twins[1].physical_row_ordinal


# ---------------------------------------------------------------------------
# Offsets resolve against raw_text (incl. multibyte unicode).
# ---------------------------------------------------------------------------

def test_offsets_resolve(fixture_parquet: Path):
    record = read_source_records(fixture_parquet, SNAPSHOT)[0]
    text = record.raw_text
    assert record.slice(0, 5) == text[0:5]
    assert record.slice(6, 11) == text[6:11]


def test_offsets_resolve_unicode(fixture_parquet: Path):
    """Character offsets index the string, so multibyte glyphs slice cleanly."""
    record = next(
        r for r in read_source_records(fixture_parquet, SNAPSHOT)
        if r.raw_text and "§" in r.raw_text
    )
    idx = record.raw_text.index("§")
    assert record.slice(idx, idx + 1) == "§"
    emoji_idx = record.raw_text.index("🜚")
    assert record.slice(emoji_idx, emoji_idx + 1) == "🜚"


def test_slice_on_null_text_raises(fixture_parquet: Path):
    null_record = next(
        r for r in read_source_records(fixture_parquet, SNAPSHOT) if r.raw_text is None
    )
    with pytest.raises(ValueError):
        null_record.slice(0, 1)


# ---------------------------------------------------------------------------
# Checksum matches the file bytes.
# ---------------------------------------------------------------------------

def test_checksum_matches_file(fixture_parquet: Path):
    record = read_source_records(fixture_parquet, SNAPSHOT)[0]
    assert record.source_file_checksum == file_sha256(fixture_parquet)


def test_checksum_verification_rejects_mismatch(fixture_parquet: Path):
    with pytest.raises(ValueError, match="checksum mismatch"):
        read_source_records(fixture_parquet, SNAPSHOT, verify_checksum="deadbeef")


# ---------------------------------------------------------------------------
# THE BOUNDARY TEST — a simulated parser improvement must require ZERO changes
# to any CanonicalSourceRecord.
# ---------------------------------------------------------------------------

def _fingerprint(record: CanonicalSourceRecord) -> tuple:
    """Everything that would have to change if the boundary were violated."""
    return (
        record.source_record_id,
        record.snapshot_version,
        record.source_file,
        record.source_file_checksum,
        record.physical_row_ordinal,
        tuple(sorted(record.original_columns.items())),
        record.raw_text,
        record.raw_text_hash,
    )


def _fake_parser(records, *, version: str, config: str) -> list[dict]:
    """A stand-in for any derived producer (identity / anatomy / hierarchy /
    classification / quality). It *reads* records and emits its own annotations;
    it must never write back into a record. Different (version, config) yield
    materially different annotations — that is the "parser improved" simulation."""
    annotations = []
    for r in records:
        body = r.raw_text or ""
        annotations.append(
            {
                "source_record_id": r.source_record_id,  # durable FK to physical row
                "producer_version": version,
                "config_hash": config,
                # a v2 "improvement" changes the derived output ...
                "operative_span": (0, len(body)) if version == "v1" else (0, len(body) // 2),
                "guess": "codified" if config == "loose" else "unknown",
            }
        )
    return annotations


def test_boundary_parser_improvement(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    before = [_fingerprint(r) for r in records]

    # Simulate two generations of an improving derived parser.
    ann_v1 = _fake_parser(records, version="v1", config="loose")
    ann_v2 = _fake_parser(records, version="v2", config="strict")

    after = [_fingerprint(r) for r in records]

    # The derived outputs genuinely differ (the "improvement" is real) ...
    assert ann_v1 != ann_v2
    # ... yet not a single byte of any source record changed.
    assert before == after
    # And a fresh read still reproduces the very same records bit-for-bit.
    reread = [_fingerprint(r) for r in read_source_records(fixture_parquet, SNAPSHOT)]
    assert reread == before
    # Derived artifacts anchor their durable FK to source_record_id (never to
    # any interpretation) — so they survive re-derivation intact.
    assert {a["source_record_id"] for a in ann_v2} == {r.source_record_id for r in records}


def test_record_is_immutable(fixture_parquet: Path):
    record = read_source_records(fixture_parquet, SNAPSHOT)[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.source_record_id = "tampered"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.raw_text = "tampered"  # type: ignore[misc]


def test_original_columns_is_read_only(fixture_parquet: Path):
    record = read_source_records(fixture_parquet, SNAPSHOT)[0]
    with pytest.raises(TypeError):
        record.original_columns["act_id"] = "tampered"  # type: ignore[index]


# ---------------------------------------------------------------------------
# Opt-in check against the committed real sample (skips if gated data absent).
# ---------------------------------------------------------------------------

def test_real_sample_roundtrip(real_sample_parquet: Path):
    import json

    pf = pq.ParquetFile(real_sample_parquet)
    n = pf.metadata.num_rows
    records = read_source_records(real_sample_parquet, SNAPSHOT)
    assert len(records) == n
    assert [r.physical_row_ordinal for r in records] == list(range(n))

    # No text lost vs. a direct read.
    direct = pq.read_table(real_sample_parquet, columns=["text"]).column("text").to_pylist()
    assert [r.raw_text for r in records] == direct

    # Checksum matches the snapshot manifest, if it's alongside the file.
    manifest = real_sample_parquet.parent / "SHA256SUMS.json"
    if manifest.exists():
        want = {
            e["file"]: e["sha256"] for e in json.loads(manifest.read_text())
        }.get(real_sample_parquet.name)
        if want is not None:
            assert records[0].source_file_checksum == want
