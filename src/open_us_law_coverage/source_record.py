"""M1A — the immutable ``CanonicalSourceRecord`` core.

Lossless, immutable serialization of the Open US Law snapshot into
``CanonicalSourceRecord`` objects. This layer carries **zero legal
interpretation of ours**: every one of the 24 source columns is preserved
verbatim (null stays null, never invented), ``raw_text`` is the source ``text``
field byte-for-byte, and the record's identity/content hashes cover
``raw_text`` + source fields **only**.

The boundary this enforces (see ``PROPOSAL.md`` "The boundary test"): nothing in
a ``CanonicalSourceRecord`` may change because our identity rules, anatomy
parser, hierarchy parser, duplicate detector, Federal-Register interpretation,
or a quality detector improved. Rebuilding any *derived* layer must have **zero**
effect on ``source_record_id`` / ``raw_text_hash``. The acceptance suite in
``tests/test_source_record.py`` tests exactly that.

Identity model (per ``PROPOSAL.md`` "Identity: four orthogonal concepts"):

* ``source_record_id`` — which physical row in which snapshot. Snapshot-local;
  deterministic from ``(snapshot_version, source_file_checksum,
  physical_row_ordinal)``. Nothing durable depends on it across snapshots, and
  it derives from **physical address only** — never from content or citation.
* ``raw_text_hash`` — content address of the raw ``text`` bytes. Over RAW bytes,
  never normalized/operative text (M0 proved USC ``text`` churns on editorial
  apparatus; binding identity to content would recreate that churn).

Deliberately boring. Everything interpretive lives in versioned annotations
downstream and anchors its durable references to ``source_record_id``.

Usage (manifest of a snapshot; cheap, no ``text`` scan)::

    uv run python -m open_us_law_coverage.source_record data/v2026.08/*.parquet \\
        --snapshot v2026.08

Non-obvious constraint carried from ``recon.py`` / ``CLAUDE.md``: the federal
``us_federal_regulations.parquet`` ``text`` column is ~11 GB with a single
row-group near ~3.3 GB. ``iter_source_records`` stays **row-group-bounded** —
one row-group of ``text`` in flight, pulling one Python string at a time and
releasing the pyarrow pool between groups — so a full-snapshot pass does not OOM
the box. Preserve that pattern in any change here.
"""

from __future__ import annotations

import argparse
import glob as globlib
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterator, Mapping, Sequence

import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Schema — the one uniform 24-column Open US Law schema (M0 finding: identical
# across all 229 files). Order is the physical column order in the Parquet.
# ---------------------------------------------------------------------------

TEXT_COLUMN = "text"

EXPECTED_COLUMNS: tuple[str, ...] = (
    "act_id",
    "citation",
    "citation_short",
    "state",
    "jurisdiction",
    "document_type",
    "title_number",
    "title_name",
    "chapter",
    "chapter_name",
    "section_number",
    "section_title",
    "breadcrumb",
    "display_path",
    "act_status",
    "text",
    "word_count",
    "source_url",
    "last_amended_year",
    "subsection_count",
    "cross_references_usc",
    "cross_references_cfr",
    "public_laws_referenced",
    "year",
)

# The 23 columns preserved verbatim in ``original_columns`` (everything but the
# ``text`` body, which is held once as ``raw_text``).
METADATA_COLUMNS: tuple[str, ...] = tuple(c for c in EXPECTED_COLUMNS if c != TEXT_COLUMN)

_FILE_HASH_CHUNK = 1 << 20  # 1 MiB — hash the file without loading it whole.


class SchemaMismatchError(ValueError):
    """Raised when a Parquet file does not carry the uniform 24-column schema."""


# ---------------------------------------------------------------------------
# Hashing / identity — pure functions so tests can recompute independently.
# ---------------------------------------------------------------------------

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_raw_text_hash(raw_text: str | None) -> str | None:
    """Content address of the raw ``text`` bytes.

    Over the **raw** UTF-8 bytes, never normalized/operative text. ``None`` text
    (losslessly preserved) hashes to ``None`` — there is nothing to address.
    """
    if raw_text is None:
        return None
    return "sha256:" + _sha256_hex(raw_text.encode("utf-8"))


def compute_source_record_id(
    snapshot_version: str,
    source_file_checksum: str,
    physical_row_ordinal: int,
) -> str:
    """Deterministic physical address of a row within a snapshot.

    Derives from physical coordinates **only** — snapshot, file checksum, and
    the row's physical ordinal — so it is independent of anything our parsers
    later conclude. A NUL domain separator keeps the components unambiguous.
    """
    payload = "\x00".join(
        (snapshot_version, source_file_checksum, str(physical_row_ordinal))
    ).encode("utf-8")
    return "srr:sha256:" + _sha256_hex(payload)


def file_sha256(path: str | Path) -> str:
    """SHA-256 of a file's bytes, read in chunks (matches the snapshot's
    ``SHA256SUMS.json`` — verified in M0)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_FILE_HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# The immutable record.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CanonicalSourceRecord:
    """One physical Parquet row, losslessly and immutably.

    Frozen: attribute assignment raises ``FrozenInstanceError``. ``original_columns``
    is a read-only ``MappingProxyType``, so the preserved columns cannot be
    mutated in place either. The record holds **no** anatomy, cleaned text,
    hierarchy assumption, or quality slot — those are versioned annotations
    elsewhere.
    """

    source_record_id: str
    snapshot_version: str
    source_file: str
    source_file_checksum: str
    physical_row_ordinal: int
    original_columns: Mapping[str, Any]
    raw_text: str | None
    raw_text_hash: str | None

    def column(self, name: str) -> Any:
        """Verbatim value of one preserved source column."""
        return self.original_columns[name]

    def slice(self, start: int, end: int) -> str:
        """Resolve a character span against ``raw_text`` (``raw_text[start:end]``).

        Character offsets index into the immutable ``raw_text`` string, so any
        span an annotation stores against this record resolves stably here.
        """
        if self.raw_text is None:
            raise ValueError(
                f"{self.source_record_id}: raw_text is null; no offsets to resolve"
            )
        return self.raw_text[start:end]


# ---------------------------------------------------------------------------
# Reader.
# ---------------------------------------------------------------------------

def _validate_schema(names: Sequence[str], source_file: str) -> None:
    got = tuple(names)
    if got != EXPECTED_COLUMNS:
        got_set, exp_set = set(got), set(EXPECTED_COLUMNS)
        missing = exp_set - got_set
        extra = got_set - exp_set
        detail = []
        if missing:
            detail.append(f"missing={sorted(missing)}")
        if extra:
            detail.append(f"extra={sorted(extra)}")
        if not detail:  # same set, wrong order — order is load-bearing for nothing,
            detail.append("column order differs from the canonical schema")  # but flag it
        raise SchemaMismatchError(
            f"{source_file}: not the uniform 24-column Open US Law schema "
            f"({'; '.join(detail)})"
        )


def iter_source_records(
    path: str | Path,
    snapshot_version: str,
    *,
    verify_checksum: str | None = None,
) -> Iterator[CanonicalSourceRecord]:
    """Stream ``CanonicalSourceRecord``s from one Parquet file, in physical order.

    ``physical_row_ordinal`` is assigned by a deterministic, insertion-preserving
    read: row groups are consumed in file order and rows in row-group order, so
    the ordinal is the stable within-file physical row index (0-based).

    Row-group-bounded (see module docstring): peak memory ≈ one row-group of
    ``text``; the pyarrow pool is released between groups. Safe on the 11 GB
    federal regulations file.

    ``verify_checksum`` (e.g. the value from ``SHA256SUMS.json``) is compared to
    the computed file checksum when given.
    """
    path = Path(path)
    source_file = path.name
    checksum = file_sha256(path)
    if verify_checksum is not None and checksum != verify_checksum:
        raise ValueError(
            f"{source_file}: checksum mismatch "
            f"(computed {checksum}, expected {verify_checksum})"
        )

    pf = pq.ParquetFile(path)
    _validate_schema([f.name for f in pf.schema_arrow], source_file)

    ordinal = 0
    for rg in range(pf.num_row_groups):
        table = pf.read_row_group(rg)
        # Metadata columns are small — pull them as Python lists once per group.
        meta_cols = {name: table.column(name).to_pylist() for name in METADATA_COLUMNS}
        # ``text`` is the giant column: index it one scalar at a time rather than
        # materializing a second full Python copy of the whole row-group.
        text_col = table.column(TEXT_COLUMN)
        n = table.num_rows
        for i in range(n):
            raw_text = text_col[i].as_py()
            metadata = {name: meta_cols[name][i] for name in METADATA_COLUMNS}
            yield CanonicalSourceRecord(
                source_record_id=compute_source_record_id(
                    snapshot_version, checksum, ordinal
                ),
                snapshot_version=snapshot_version,
                source_file=source_file,
                source_file_checksum=checksum,
                physical_row_ordinal=ordinal,
                original_columns=MappingProxyType(metadata),
                raw_text=raw_text,
                raw_text_hash=compute_raw_text_hash(raw_text),
            )
            ordinal += 1
        # Keep peak ≈ one row-group: drop references and hand the arena back.
        del table, meta_cols, text_col
        import pyarrow as pa  # local import keeps the hot path's namespace tidy

        pa.default_memory_pool().release_unused()


def read_source_records(
    path: str | Path,
    snapshot_version: str,
    *,
    verify_checksum: str | None = None,
) -> list[CanonicalSourceRecord]:
    """Eager convenience wrapper over :func:`iter_source_records`.

    Materializes every record (and therefore every ``raw_text``) in memory — fine
    for the small sample/fixture files the tests use; **do not** call it on the
    full federal regulations file. Use :func:`iter_source_records` there.
    """
    return list(iter_source_records(path, snapshot_version, verify_checksum=verify_checksum))


# ---------------------------------------------------------------------------
# CLI — a cheap snapshot manifest (row counts, checksums, boundary ids). No
# ``text`` scan: counts come from Parquet metadata.
# ---------------------------------------------------------------------------

def _load_checksum_manifest(files: Sequence[Path]) -> dict[str, str]:
    """Best-effort ``SHA256SUMS.json`` lookup, keyed by file name, if one sits
    beside the Parquet files."""
    for f in files:
        candidate = f.parent / "SHA256SUMS.json"
        if candidate.exists():
            try:
                entries = json.loads(candidate.read_text())
                return {e["file"]: e["sha256"] for e in entries}
            except (json.JSONDecodeError, KeyError, TypeError):
                return {}
    return {}


def build_manifest(paths: Sequence[str], snapshot_version: str) -> list[dict[str, Any]]:
    files = sorted({Path(p) for pat in paths for p in globlib.glob(pat)})
    declared = _load_checksum_manifest(files)
    out: list[dict[str, Any]] = []
    for path in files:
        pf = pq.ParquetFile(path)
        names = [f.name for f in pf.schema_arrow]
        schema_ok = tuple(names) == EXPECTED_COLUMNS
        checksum = file_sha256(path)
        n_rows = pf.metadata.num_rows
        entry: dict[str, Any] = {
            "source_file": path.name,
            "rows": n_rows,
            "row_groups": pf.num_row_groups,
            "source_file_checksum": checksum,
            "schema_ok": schema_ok,
        }
        want = declared.get(path.name)
        if want is not None:
            entry["checksum_matches_manifest"] = want == checksum
        if n_rows > 0:
            entry["first_source_record_id"] = compute_source_record_id(
                snapshot_version, checksum, 0
            )
            entry["last_source_record_id"] = compute_source_record_id(
                snapshot_version, checksum, n_rows - 1
            )
        out.append(entry)
    return out


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="M1A: emit a manifest of CanonicalSourceRecord coordinates "
        "for Open US Law Parquet files (row counts, checksums, boundary ids). "
        "Does not scan the text column."
    )
    ap.add_argument("paths", nargs="+", help="Parquet file(s) or glob(s)")
    ap.add_argument("--snapshot", required=True, help="snapshot version, e.g. v2026.08")
    args = ap.parse_args(argv)
    manifest = build_manifest(args.paths, args.snapshot)
    print(json.dumps({"snapshot_version": args.snapshot, "files": manifest}, indent=2))


if __name__ == "__main__":
    main()
