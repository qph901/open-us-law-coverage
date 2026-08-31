"""M1A.5 closure C.3 — the full-snapshot identity manifest harness.

Hermetic: a small synthetic ``us_federal_regulations``-shaped Parquet with real
``act_id`` collisions (a CFR group with a byte-identical pair, an FR group, and a
1:1 CFR row) exercises the two-pass manifest — text-free group sizing plus the real
collision producers and within-group duplicate detection.
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from open_us_law_coverage.identity_manifest import (
    CollisionDeepDive,
    _connect,
    add_collision_file,
    build_manifest,
    scan_group_sizes,
)
from open_us_law_coverage.source_record import EXPECTED_COLUMNS


@pytest.fixture()
def con(tmp_path: Path):
    return _connect("1GB", tmp_path / "spill")

_INT_COLUMNS = {"word_count", "last_amended_year", "subsection_count", "year"}
_DUP = "Identical regulatory body."


def _row(act_id: str, text: str | None, ordinal_hint: str) -> dict[str, object]:
    base = {name: None for name in EXPECTED_COLUMNS}
    base.update(
        act_id=act_id,
        citation=f"cite {ordinal_hint}",
        state="US",
        jurisdiction="US",
        document_type="regulation",
        breadcrumb=f"Reg > {ordinal_hint}",
        display_path=ordinal_hint,
        act_status="in_force",
        text=text,
        word_count=3,
        subsection_count=0,
        year=2026,
    )
    return base


# CFR act_id repeated 3x (two byte-identical); FR act_id repeated 2x (distinct); one
# 1:1 CFR row.
_ROWS = [
    _row("CFR_T17_P240_S240.10b-5", "segment one", "a"),
    _row("CFR_T17_P240_S240.10b-5", _DUP, "b"),
    _row("CFR_T17_P240_S240.10b-5", _DUP, "c"),  # byte-identical to row b
    _row("FR_2026_00001", "notice one", "d"),
    _row("FR_2026_00001", "notice two", "e"),
    _row("CFR_T40_P1_S1.1", "standalone", "f"),  # 1:1
]


@pytest.fixture(scope="module")
def regs_parquet(tmp_path_factory: pytest.TempPathFactory) -> Path:
    fields = [
        pa.field(n, pa.int64() if n in _INT_COLUMNS else pa.string())
        for n in EXPECTED_COLUMNS
    ]
    table = pa.table(
        {n: [r[n] for r in _ROWS] for n in EXPECTED_COLUMNS}, schema=pa.schema(fields)
    )
    path = tmp_path_factory.mktemp("manifest") / "us_federal_regulations.parquet"
    pq.write_table(table, path, row_group_size=2)
    return path


def test_manifest_hash_matches_canonical_pipeline_and_no_tripwire(
    con, regs_parquet: Path
):
    """Finding P1-1: the manifest's ``raw_text_hash`` must be the exact canonical
    format (``"sha256:" + sha256(raw UTF-8 text)``), not a bare ``md5``. Proven by
    building identity members for the same physical rows two ways — the DuckDB manifest
    path and the canonical ``CanonicalSourceRecord`` path — and showing they produce
    identical member-annotation ``artifact_id`` **and** ``payload_hash``, so the D2
    collision tripwire stays silent across the two paths (a bare md5 made it fire)."""
    from collections import defaultdict

    from open_us_law_coverage.derived import (
        check_payload_collisions,
        identity_member,
        regulations_identity_group,
    )
    from open_us_law_coverage.identity_manifest import _colliding_members
    from open_us_law_coverage.source_record import read_source_records

    manifest_buckets = _colliding_members(con, regs_parquet, "v2026.08")
    assert manifest_buckets  # the fixture has colliding groups

    canon_by_act: dict[str, list] = defaultdict(list)
    for rec in read_source_records(regs_parquet, "v2026.08"):
        canon_by_act[rec.column("act_id")].append(identity_member(rec))

    all_artifacts = []
    for act_id, m_members in manifest_buckets.items():
        c_members = canon_by_act[act_id]
        # same physical rows recovered by both paths
        assert {m.source_record_id for m in m_members} == {
            c.source_record_id for c in c_members
        }
        # identical canonical raw_text_hash per physical row
        m_hash = {m.source_record_id: m.raw_text_hash for m in m_members}
        c_hash = {c.source_record_id: c.raw_text_hash for c in c_members}
        assert m_hash == c_hash
        for h in c_hash.values():
            assert h is None or h.startswith("sha256:")

        m_res = regulations_identity_group(m_members)
        c_res = regulations_identity_group(c_members)
        assert m_res.group.provenance.artifact_id == c_res.group.provenance.artifact_id
        assert m_res.group.payload_hash == c_res.group.payload_hash
        # members are ordered by physical row, so the two paths align member-for-member
        for ma, ca in zip(m_res.members, c_res.members, strict=True):
            assert ma.provenance.artifact_id == ca.provenance.artifact_id
            assert ma.payload_hash == ca.payload_hash
        all_artifacts += [m_res.group, c_res.group, *m_res.members, *c_res.members]

    # equal ids across both paths -> equal payloads: the tripwire has nothing to fire.
    check_payload_collisions(all_artifacts)


def test_scan_group_sizes_is_text_free_and_correct(con, regs_parquet: Path):
    rows, counts = scan_group_sizes(con, regs_parquet)
    assert rows == 6
    assert counts["CFR_T17_P240_S240.10b-5"] == 3
    assert counts["FR_2026_00001"] == 2
    assert counts["CFR_T40_P1_S1.1"] == 1


def test_collision_deep_dive_runs_real_producers(con, regs_parquet: Path):
    _, counts = scan_group_sizes(con, regs_parquet)
    dive = CollisionDeepDive()
    add_collision_file(dive, con, regs_parquet, "v2026.08", counts)
    # one multi-member CFR group (3 rows), one multi-member FR group (2 rows).
    assert dive.multi_groups_by_strategy["cfr_identity_v1"] == 1
    assert dive.multi_rows_by_strategy["cfr_identity_v1"] == 3
    assert dive.multi_groups_by_strategy["federal_register_document_v1"] == 1
    assert dive.multi_rows_by_strategy["federal_register_document_v1"] == 2
    # the byte-identical CFR pair are both flagged within the group; the FR rows and
    # the distinct CFR segment are not.
    assert dive.within_group_duplicate_rows == 2
    # statuses: CFR multi -> provisional, FR multi -> ambiguous, 1:1 CFR -> resolved.
    assert dive.status_groups["provisional"] == 1
    assert dive.status_groups["ambiguous"] == 1
    assert dive.status_groups["resolved"] == 1
    assert dive.max_group_size == 3


def test_state_regulation_collisions_route_to_state_strategy(con, tmp_path: Path):
    """C.3 finding: STATE_* administrative-code collisions are real; they route to
    state_regulation_v1 (provisional multi-segment), not to CFR/FR."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [
        _row("STATE_OH_ADC_117_3_11", "seg one", "a"),
        _row("STATE_OH_ADC_117_3_11", "seg two", "b"),  # collision
        _row("STATE_OH_ADC_999_1", "solo", "c"),
    ]
    fields = [
        pa.field(n, pa.int64() if n in _INT_COLUMNS else pa.string())
        for n in EXPECTED_COLUMNS
    ]
    table = pa.table(
        {n: [r[n] for r in rows] for n in EXPECTED_COLUMNS}, schema=pa.schema(fields)
    )
    path = tmp_path / "us_oh_regulations.parquet"
    pq.write_table(table, path, row_group_size=2)

    _, counts = scan_group_sizes(con, path)
    dive = CollisionDeepDive()
    add_collision_file(dive, con, path, "v2026.08", counts)
    assert dive.multi_groups_by_strategy["state_regulation_v1"] == 1
    assert dive.multi_rows_by_strategy["state_regulation_v1"] == 2
    assert dive.status_groups["provisional"] == 1
    assert dive.status_groups["resolved"] == 1  # the solo STATE_OH_ADC_999_1


def test_build_manifest_detects_the_collision_file(regs_parquet: Path, tmp_path: Path):
    res = build_manifest([regs_parquet], "v2026.08", temp_dir=tmp_path / "spill")
    assert res.total_rows == 6
    assert res.total_groups == 3  # three distinct act_ids
    assert res.collision_files == [regs_parquet.name]
    assert res.regulations is not None
    reg = res.corpora["regulations"]
    assert reg.multi_member_groups == 2  # the CFR-3 and FR-2 groups
    assert reg.single_member_groups == 1
    assert reg.max_group_size == 3


def test_all_11_file_has_no_collisions_and_no_deep_dive(fixture_parquet: Path, tmp_path: Path):
    """A 1:1 fixture (distinct act_ids) yields all single-member groups, no collision
    file, and no regulations deep-dive."""
    res = build_manifest([fixture_parquet], "v2026.08", temp_dir=tmp_path / "spill")
    assert res.collision_files == []
    assert res.regulations is None
    only = next(iter(res.corpora.values()))
    assert only.multi_member_groups == 0
    assert only.single_member_groups == only.groups
