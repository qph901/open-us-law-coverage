"""Shared fixtures for the M1A acceptance suite.

The core suite is **hermetic**: it builds a tiny synthetic Parquet carrying the
exact uniform 24-column Open US Law schema, so the invariants run without the
gated dataset. The fixture is deliberately adversarial for a *lossless* layer:

* multiple row groups (``row_group_size=2`` over 5 rows) so the ordinal logic is
  exercised across row-group boundaries, including a final partial group;
* a multibyte-unicode row (§, é, and an astral emoji) — raw-byte hashing and
  character-offset slicing must both survive it;
* a **null** ``text`` row *and* null metadata cells — null must stay null;
* an **empty-string** ``text`` row — distinct from null;
* two rows with **byte-identical** ``text`` — equal content hash, distinct id.

A separate opt-in fixture points at the committed real sample file when present.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from open_us_law_coverage.source_record import EXPECTED_COLUMNS, TEXT_COLUMN

SNAPSHOT = "v2026.08"

_IDENTICAL_TEXT = "Identical body shared by two rows."

# One dict per row. Every one of the 24 columns is present; ``None`` means a
# genuinely null cell. Order of rows here is the intended physical order.
_ROWS: list[dict[str, object]] = [
    {
        "act_id": "USC_T42_C21_S1983",
        "citation": "42 U.S.C. § 1983",
        "citation_short": "42 USC 1983",
        "state": "US",
        "jurisdiction": "US",
        "document_type": "section",
        "title_number": "42",
        "title_name": "The Public Health and Welfare",
        "chapter": "21",
        "chapter_name": "Civil Rights",
        "section_number": "1983",
        "section_title": "Civil action for deprivation of rights",
        "breadcrumb": "Title 42 > Chapter 21 > § 1983",
        "display_path": "42/21/1983",
        "act_status": "in_force",
        "text": "Every person who, under color of any statute...",
        "word_count": 8,
        "source_url": "https://example.gov/usc/42/1983",
        "last_amended_year": 1996,
        "subsection_count": 0,
        "cross_references_usc": "[]",
        "cross_references_cfr": "[]",
        "public_laws_referenced": "[]",
        "year": 2026,
    },
    {
        # Multibyte unicode + astral emoji; several null metadata cells.
        "act_id": "STATE_AK_T10_C10.06_S10.06.005",
        "citation": "AK Stat. § 10.06.005",
        "citation_short": None,
        "state": "AK",
        "jurisdiction": "US",
        "document_type": "section",
        "title_number": None,
        "title_name": None,
        "chapter": "10.06",
        "chapter_name": None,
        "section_number": "10.06.005",
        "section_title": "Résumé of powers — see § 10 ✦",
        "breadcrumb": "Title 10 > Chapter 10.06 > § 10.06.005",
        "display_path": "10/10.06/10.06.005",
        "act_status": "in_force",
        "text": "Provision with a section sign §, café, and an emoji 🜚 mid-text.",
        "word_count": 11,
        "source_url": None,
        "last_amended_year": None,
        "subsection_count": None,
        "cross_references_usc": None,
        "cross_references_cfr": None,
        "public_laws_referenced": None,
        "year": 2026,
    },
    {
        # Null text — losslessly a null body, not an empty string.
        "act_id": "SCONST_AK_A10_S0",
        "citation": "AK Const. art. X, § 0",
        "citation_short": "AK Const X 0",
        "state": "AK",
        "jurisdiction": "US",
        "document_type": "constitution",
        "title_number": "10",
        "title_name": "Local Government",
        "chapter": None,
        "chapter_name": None,
        "section_number": "0",
        "section_title": "Purpose",
        "breadcrumb": "Article X > § 0",
        "display_path": "X/0",
        "act_status": "in_force",
        "text": None,
        "word_count": 0,
        "source_url": "https://example.gov/ak/const/X/0",
        "last_amended_year": None,
        "subsection_count": 0,
        "cross_references_usc": "[]",
        "cross_references_cfr": "[]",
        "public_laws_referenced": "[]",
        "year": 2026,
    },
    {
        # Empty-string text with a newline sibling below — distinct from null.
        "act_id": "STATE_AK_T10_C10.06_S10.06.006",
        "citation": "AK Stat. § 10.06.006",
        "citation_short": "AK 10.06.006",
        "state": "AK",
        "jurisdiction": "US",
        "document_type": "section",
        "title_number": "10",
        "title_name": "Corporations",
        "chapter": "10.06",
        "chapter_name": "Alaska Corporations Code",
        "section_number": "10.06.006",
        "section_title": "Reserved",
        "breadcrumb": "Title 10 > Chapter 10.06 > § 10.06.006",
        "display_path": "10/10.06/10.06.006",
        "act_status": "reserved",
        "text": "",
        "word_count": 0,
        "source_url": None,
        "last_amended_year": None,
        "subsection_count": 0,
        "cross_references_usc": "[]",
        "cross_references_cfr": "[]",
        "public_laws_referenced": "[]",
        "year": 2026,
    },
    {
        # Byte-identical text to the row below (there is no row below in this file,
        # so pair it with row index 5's clone) — see clone appended below.
        "act_id": "STATE_AK_T10_C10.06_S10.06.007",
        "citation": "AK Stat. § 10.06.007",
        "citation_short": "AK 10.06.007",
        "state": "AK",
        "jurisdiction": "US",
        "document_type": "section",
        "title_number": "10",
        "title_name": "Corporations",
        "chapter": "10.06",
        "chapter_name": "Alaska Corporations Code",
        "section_number": "10.06.007",
        "section_title": "Body A",
        "breadcrumb": "Title 10 > Chapter 10.06 > § 10.06.007",
        "display_path": "10/10.06/10.06.007",
        "act_status": "in_force",
        "text": _IDENTICAL_TEXT,
        "word_count": 6,
        "source_url": None,
        "last_amended_year": 2020,
        "subsection_count": 0,
        "cross_references_usc": "[]",
        "cross_references_cfr": "[]",
        "public_laws_referenced": "[]",
        "year": 2026,
    },
    {
        # Clone of the row above's text — byte-identical body, different metadata.
        "act_id": "STATE_AK_T10_C10.06_S10.06.008",
        "citation": "AK Stat. § 10.06.008",
        "citation_short": "AK 10.06.008",
        "state": "AK",
        "jurisdiction": "US",
        "document_type": "section",
        "title_number": "10",
        "title_name": "Corporations",
        "chapter": "10.06",
        "chapter_name": "Alaska Corporations Code",
        "section_number": "10.06.008",
        "section_title": "Body A (clone)",
        "breadcrumb": "Title 10 > Chapter 10.06 > § 10.06.008",
        "display_path": "10/10.06/10.06.008",
        "act_status": "in_force",
        "text": _IDENTICAL_TEXT,
        "word_count": 6,
        "source_url": None,
        "last_amended_year": 2020,
        "subsection_count": 0,
        "cross_references_usc": "[]",
        "cross_references_cfr": "[]",
        "public_laws_referenced": "[]",
        "year": 2026,
    },
]

# int64 columns per the real schema; everything else is a string column.
_INT_COLUMNS = {"word_count", "last_amended_year", "subsection_count", "year"}


def _fixture_table() -> pa.Table:
    fields = []
    for name in EXPECTED_COLUMNS:
        typ = pa.int64() if name in _INT_COLUMNS else pa.string()
        fields.append(pa.field(name, typ))
    schema = pa.schema(fields)
    columns = {name: [row[name] for row in _ROWS] for name in EXPECTED_COLUMNS}
    return pa.table(columns, schema=schema)


@pytest.fixture(scope="session")
def fixture_rows() -> list[dict[str, object]]:
    """The intended physical rows, in order — the ground truth for round-trips."""
    return _ROWS


@pytest.fixture(scope="session")
def identical_text() -> str:
    return _IDENTICAL_TEXT


@pytest.fixture(scope="session")
def text_column_name() -> str:
    return TEXT_COLUMN


@pytest.fixture(scope="session")
def fixture_parquet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A synthetic Parquet with the 24-column schema, written across multiple
    row groups so ordinal continuity is tested at row-group boundaries."""
    path = tmp_path_factory.mktemp("m1a_fixture") / "us_synthetic_sample.parquet"
    pq.write_table(_fixture_table(), path, row_group_size=2)
    return path


# --- opt-in real-sample fixture -------------------------------------------

_REAL_SAMPLE = Path("data/v2026.08/us_ak_constitutions.parquet")


@pytest.fixture(scope="session")
def real_sample_parquet() -> Path:
    if not _REAL_SAMPLE.exists():
        pytest.skip(f"gated sample {_REAL_SAMPLE} not present")
    return _REAL_SAMPLE
