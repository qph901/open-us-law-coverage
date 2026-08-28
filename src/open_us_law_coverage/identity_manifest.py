"""M1A.5 closure C.3 — the deterministic full-snapshot identity manifest.

The first end-to-end evidence that the identity layer behaves **at scale**, and the
natural regression fixture for the next snapshot. Over the full v2026.08 snapshot it
reports, per corpus: rows, groups (distinct ``act_id``), the group-size distribution,
collision counts, within-group duplicate rows, and the ambiguity / abstention rate —
the outputs of the concrete strategies (Phase B) run across every file.

**OOM invariant (CLAUDE.md).** The federal regulations file has an ~11 GB ``text``
column in a single ~3.3 GB row-group; materializing a row-group OOM-kills the box.
So *all* ``text`` work goes through **DuckDB** with a hard ``memory_limit`` + disk
spill (the same path :mod:`.identity_collisions` / :mod:`.segment_provenance` use),
never pyarrow ``read_row_group``:

* group sizing is ``COUNT(*) GROUP BY act_id`` (reads only the small ``act_id``
  column) for every file;
* for files where ``act_id`` repeats — M0 established that is **only**
  ``us_federal_regulations`` — the colliding rows' ``(file_row_number, act_id,
  md5(text))`` are streamed out (``md5(text)`` streams over the whole column and
  spills; a ``SEMI JOIN`` returns only the colliding rows, a small set), lifted into
  lightweight :class:`~.derived.identity_strategies.IdentityMember`\\ s, and fed to
  the real ``cfr_identity_v1`` / ``federal_register_document_v1`` producers plus
  ``detect_duplicate_rows`` *within each group*. Peak memory stays at
  ``memory_limit``; no ``text`` bytes ever reach Python.

Regenerate (byte-stable)::

    uv run python -m open_us_law_coverage.identity_manifest \\
        data/v2026.08_full/*.parquet --snapshot v2026.08 \\
        --out reports/M1A5_identity_manifest.md \\
        --memory-limit 4GB --temp-dir /path/to/scratch/ddspill
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import duckdb

from .derived import detect_duplicate_rows, is_duplicate_row
from .derived.identity import IdentityStatus
from .derived.identity_strategies import (
    IdentityMember,
    act_id_prefix,
    corpus_of_source_file,
    regulations_identity_group,
)
from .source_record import compute_source_record_id, file_sha256


@dataclass
class CorpusStats:
    corpus: str
    files: int = 0
    rows: int = 0
    groups: int = 0
    single_member_groups: int = 0
    multi_member_groups: int = 0
    max_group_size: int = 0
    collision_rows: int = 0  # rows in multi-member groups


@dataclass
class CollisionDeepDive:
    """The real-producer analysis of every file where ``act_id`` collides.

    Aggregated across **all** collision files (C.3 surfaced that collisions are not
    federal-only — state administrative codes collide too), routed per group by
    :func:`~.derived.identity_strategies.regulations_identity_group`.
    """

    collision_files: list[str] = field(default_factory=list)
    multi_groups_by_strategy: Counter = field(default_factory=Counter)
    multi_rows_by_strategy: Counter = field(default_factory=Counter)
    within_group_duplicate_rows: int = 0
    single_member_groups: int = 0  # 1:1 groups within the collision files
    status_groups: Counter = field(default_factory=Counter)  # by identity_status
    group_size_hist: Counter = field(default_factory=Counter)  # size -> n groups
    max_group_size: int = 0


@dataclass
class ManifestResult:
    snapshot: str
    total_files: int = 0
    total_rows: int = 0
    total_groups: int = 0
    corpora: dict[str, CorpusStats] = field(default_factory=dict)
    collision_files: list[str] = field(default_factory=list)
    regulations: CollisionDeepDive | None = None


def _connect(memory_limit: str, temp_dir: Path) -> duckdb.DuckDBPyConnection:
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute(f"SET temp_directory='{temp_dir.as_posix()}'")
    con.execute("SET threads=1")
    con.execute("SET preserve_insertion_order=true")
    return con


def scan_group_sizes(
    con: duckdb.DuckDBPyConnection, path: Path
) -> tuple[int, dict[str, int]]:
    """Return ``(rows, {act_id: count})`` reading only the ``act_id`` column."""
    rows = con.execute(
        "SELECT act_id, COUNT(*) FROM read_parquet(?) GROUP BY act_id",
        [path.as_posix()],
    ).fetchall()
    counts = {aid: c for aid, c in rows}
    return sum(counts.values()), counts


def _colliding_members(
    con: duckdb.DuckDBPyConnection, path: Path, snapshot: str
) -> dict[str, list[IdentityMember]]:
    """The members of every colliding ``act_id`` group, as lightweight views.

    ``md5(text)`` streams over the whole ``text`` column (spilling under the memory
    limit); the ``SEMI JOIN`` returns only rows whose ``act_id`` repeats, so no
    ``text`` bytes and only a small result reach Python. ``source_record_id`` is the
    real M1A id (``file_row_number`` is the physical row ordinal)."""
    checksum = file_sha256(path)
    corpus = corpus_of_source_file(path.name)
    q = """
    WITH b AS (
        SELECT file_row_number AS frn, act_id, state, document_type, md5(text) AS h
        FROM read_parquet(?, file_row_number=true)
    ),
    dup AS (SELECT act_id FROM b GROUP BY act_id HAVING COUNT(*) > 1)
    SELECT b.frn, b.act_id, b.state, b.document_type, b.h
    FROM b SEMI JOIN dup USING (act_id)
    ORDER BY b.act_id, b.frn
    """
    buckets: dict[str, list[IdentityMember]] = defaultdict(list)
    for frn, act_id, state, document_type, h in con.execute(
        q, [path.as_posix()]
    ).fetchall():
        buckets[act_id].append(
            IdentityMember(
                source_record_id=compute_source_record_id(snapshot, checksum, int(frn)),
                act_id=act_id,
                state=state,
                corpus=corpus,
                document_type=document_type,
                raw_text_hash=h,
                physical_row_ordinal=int(frn),
            )
        )
    return buckets


def add_collision_file(
    dive: CollisionDeepDive,
    con: duckdb.DuckDBPyConnection,
    path: Path,
    snapshot: str,
    counts: dict[str, int],
) -> None:
    """Fold one collision file into the aggregate deep-dive: run the real router +
    within-group duplicate detection over its colliding groups, and count its
    single-member groups from the cheap sizing pass."""
    dive.collision_files.append(path.name)

    # Single-member groups are 1:1 (resolved) — counted from the sizing pass.
    for size in counts.values():
        dive.group_size_hist[size] += 1
        dive.max_group_size = max(dive.max_group_size, size)
        if size == 1:
            dive.single_member_groups += 1
            dive.status_groups[str(IdentityStatus.RESOLVED)] += 1

    for act_id, members in _colliding_members(con, path, snapshot).items():
        size = len(members)
        result = regulations_identity_group(members)  # routes by namespace
        strategy = result.group.strategy_name
        dive.multi_groups_by_strategy[strategy] += 1
        dive.multi_rows_by_strategy[strategy] += size
        dive.status_groups[str(result.group.identity_status)] += 1
        # duplicate_row WITHIN this group only (never across groups).
        dup = detect_duplicate_rows(members)
        dive.within_group_duplicate_rows += sum(
            1 for a in dup.annotations if is_duplicate_row(a)
        )


def build_manifest(
    paths: Sequence[Path],
    snapshot: str,
    *,
    memory_limit: str = "4GB",
    temp_dir: Path = Path(".duckdb_spill"),
) -> ManifestResult:
    res = ManifestResult(snapshot=snapshot)
    con = _connect(memory_limit, temp_dir)
    collision_counts: dict[str, dict[str, int]] = {}
    for path in sorted(paths):
        rows, counts = scan_group_sizes(con, path)
        corpus = corpus_of_source_file(path.name)
        cs = res.corpora.setdefault(corpus, CorpusStats(corpus=corpus))
        cs.files += 1
        cs.rows += rows
        cs.groups += len(counts)
        for size in counts.values():
            if size == 1:
                cs.single_member_groups += 1
            else:
                cs.multi_member_groups += 1
                cs.collision_rows += size
            cs.max_group_size = max(cs.max_group_size, size)
        res.total_files += 1
        res.total_rows += rows
        res.total_groups += len(counts)
        if any(size > 1 for size in counts.values()):
            res.collision_files.append(path.name)
            collision_counts[path.name] = counts

    # Deep-dive every collision file with the real producers, aggregated
    # deterministically (sorted) into one CollisionDeepDive.
    if res.collision_files:
        dive = CollisionDeepDive()
        for name in sorted(res.collision_files):
            path = next(p for p in paths if p.name == name)
            add_collision_file(dive, con, path, snapshot, collision_counts[name])
        res.regulations = dive
    return res


# ---------------------------------------------------------------------------
# Report.
# ---------------------------------------------------------------------------

EXIT_SECTION = """\
## What this establishes

- **Identity is 1:1 outside the regulations corpora** — every statute,
  constitution, court-rule, and guidance file is entirely single-member groups, so
  the 1:1 strategies cover the overwhelming majority of the snapshot.
- **`act_id` collisions are a *regulations* phenomenon, and not federal-only** — a
  finding this manifest surfaced: alongside `us_federal_regulations` (CFR + FR),
  several **state administrative-code** corpora repeat an `act_id` across rows. The
  router splits every collision group by namespace: CFR / state-regulation →
  `provisional` multi-segment candidates (assembly/anatomy confirms, CFR-A2); FR →
  `ambiguous` co-numbered captures that are never composed.
- **`duplicate_row` is scoped to the group.** Within-group duplicate rows are
  counted by the real `detect_duplicate_rows` run inside each group — never across
  groups, so byte-identical text under *different* `act_id`s is not conflated (the
  M0.5B3 content-vs-identity finding, confirmed at snapshot scale).
- **Abstention is a first-class, measured outcome**, not an error: the FR
  `ambiguous` rate is reported, and a `provisional`/`ambiguous` group is a safe
  non-composition, not a failure.

This report is byte-stable and is the regression fixture for the next
regulations-bearing snapshot.
"""


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.2f}%" if b else "—"


def render_report(res: ManifestResult) -> str:
    L: list[str] = []
    L.append("# M1A.5 — full-snapshot identity manifest")
    L.append("")
    L.append(f"Snapshot: **{res.snapshot}**. Files: **{res.total_files}**. Rows: "
             f"**{res.total_rows:,}**. Identity groups (distinct `act_id` per file): "
             f"**{res.total_groups:,}**. Produced by the concrete Phase-B strategies "
             "run over every file (`act_id`-only sizing for all; the real collision "
             "producers + within-group `detect_duplicate_rows` where `act_id` repeats).")
    L.append("")
    L.append("## Per-corpus group structure")
    L.append("")
    L.append("| corpus | files | rows | groups | single-member | multi-member | max size |")
    L.append("|---|--:|--:|--:|--:|--:|--:|")
    for corpus in sorted(res.corpora):
        cs = res.corpora[corpus]
        L.append(
            f"| `{cs.corpus}` | {cs.files} | {cs.rows:,} | {cs.groups:,} | "
            f"{cs.single_member_groups:,} ({_pct(cs.single_member_groups, cs.groups)}) | "
            f"{cs.multi_member_groups:,} | {cs.max_group_size} |"
        )
    L.append("")
    total_single = sum(c.single_member_groups for c in res.corpora.values())
    L.append(f"- **{_pct(total_single, res.total_groups)}** of all groups are "
             f"single-member (1:1 source→document); multi-member groups: "
             f"**{res.total_groups - total_single:,}**.")
    L.append(f"- collision files (any `act_id` repeats): "
             + (", ".join(f"`{f}`" for f in res.collision_files) or "none"))
    L.append("")

    if res.regulations is not None:
        d = res.regulations
        L.append("## Regulations collision deep-dive (real producers)")
        L.append("")
        L.append("Aggregated across every collision file: "
                 + ", ".join(f"`{f}`" for f in sorted(d.collision_files))
                 + ". Multi-member groups are the only place identity composes more "
                 "than one row — and even there it *groups*, never *concatenates*.")
        L.append("")
        L.append("| strategy (namespace) | multi-member groups | rows |")
        L.append("|---|--:|--:|")
        for strategy in sorted(d.multi_groups_by_strategy):
            L.append(f"| `{strategy}` | {d.multi_groups_by_strategy[strategy]:,} | "
                     f"{d.multi_rows_by_strategy[strategy]:,} |")
        L.append("")
        L.append(f"- **within-group duplicate rows** (real `detect_duplicate_rows`, "
                 f"per group): **{d.within_group_duplicate_rows:,}**.")
        L.append(f"- single-member (1:1) groups within the collision files: "
                 f"**{d.single_member_groups:,}**.")
        L.append(f"- **max group size**: {d.max_group_size}.")
        L.append("- group `identity_status`: "
                 + ", ".join(f"`{k}`:{v:,}" for k, v in sorted(d.status_groups.items())))
        total_reg_groups = sum(d.status_groups.values())
        ambiguous = d.status_groups.get(str(IdentityStatus.AMBIGUOUS), 0)
        L.append(f"- **abstention/ambiguity rate** (ambiguous groups / groups in "
                 f"collision files): {_pct(ambiguous, total_reg_groups)}.")
        L.append("")
        L.append("### Group-size distribution (collision files)")
        L.append("")
        L.append("| group size | groups |")
        L.append("|--:|--:|")
        for size in sorted(d.group_size_hist):
            L.append(f"| {size} | {d.group_size_hist[size]:,} |")
        L.append("")

    L.append(EXIT_SECTION)
    return "\n".join(L) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="M1A.5 C.3: deterministic full-snapshot identity manifest."
    )
    ap.add_argument("paths", nargs="+", help="snapshot Parquet files (a glob)")
    ap.add_argument("--snapshot", required=True, help="snapshot version, e.g. v2026.08")
    ap.add_argument("--out", help="write the Markdown report here (else stdout)")
    ap.add_argument("--memory-limit", default="4GB", help="DuckDB memory cap")
    ap.add_argument("--temp-dir", type=Path, default=Path(".duckdb_spill"),
                    help="DuckDB spill directory")
    args = ap.parse_args(argv)

    res = build_manifest(
        [Path(p) for p in args.paths],
        args.snapshot,
        memory_limit=args.memory_limit,
        temp_dir=args.temp_dir,
    )
    report = render_report(res)
    if args.out:
        Path(args.out).write_text(report)
        print(f"wrote {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
