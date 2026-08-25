"""M0.5A identity-collision analysis for the Open US Law snapshot.

M0 established that ``act_id`` is 100% populated in every corpus but **not
unique** within ``us_federal_regulations.parquet``. That single fact blocks the
source-identity contract: no shared key may assume ``act_id`` alone identifies a
row. This harness enumerates every corpus whose ``act_id`` repeats and — the
point the proposal insists on — *explains each collision class as a phenomenon
before proposing a key*, so a composite key can't quietly make a semantic bug
"unique."

For each colliding file it reports, per ``act_id`` namespace (the leading
alphabetic prefix, e.g. ``CFR`` vs ``FR``), how many collision groups have:

  * every row's ``text`` IDENTICAL   -> literal duplicate rows (ETL duplication);
  * every row's ``text`` DISTINCT    -> genuine multi-segment split of one source
                                        document / section;
  * a mix (``partial``)              -> a segmented document that also carries a
                                        duplicate.

plus whether ``source_url`` and ``word_count`` ever discriminate rows within a
group. These distinguish the proposal's hypothesized causes (a) same act_id +
different segment rows, (b) act_id reused by upstream ETL, (c) one act_id shared
across related regulatory documents.

Memory note: ``us_federal_regulations.parquet`` has an ~11 GB ``text`` column
with a single 3.3 GB row-group. polars (in-memory and streaming) and pyarrow
``read_row_group`` all materialize a whole row-group, which OOM-kills a 14 GB
box mid-scan. DuckDB streams the column in vectors and spills the distinct-hash
aggregate to ``--temp-dir`` under a hard ``--memory-limit``, so the collision
counts compute without ever holding a row-group. Keep aggregation over ``text``
on this file in DuckDB for that reason.

Usage:
    uv run python -m open_us_law_coverage.identity_collisions \
        data/v2026.08_full/*.parquet --snapshot v2026.08 \
        --out reports/M0.5A_identity_collisions.md
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

# Columns every file shares (M0: one uniform 24-column schema). We only touch a
# handful; text is read solely to hash it per row.
TEXT_COL = "text"


@dataclass
class NamespaceCollisions:
    """Collision breakdown for one act_id namespace within one file."""

    namespace: str
    groups: int
    rows: int
    all_identical: int  # every row in the group has identical text -> ETL dup
    all_distinct: int   # every row distinct text -> real multi-segment split
    partial: int        # mixed: a segmented doc that also carries a dup
    same_url: int       # groups where source_url never varies within the group
    same_wordcount: int  # groups where word_count never varies within the group
    max_group: int
    example_identical: str | None
    example_distinct: str | None


@dataclass
class FileCollisions:
    """Per-file collision summary."""

    name: str
    total_rows: int
    distinct_ids: int
    null_ids: int
    collision_rows: int  # rows beyond one-per-distinct act_id
    namespaces: list[NamespaceCollisions] = field(default_factory=list)

    @property
    def has_collisions(self) -> bool:
        return self.collision_rows > 0


def _connect(memory_limit: str, temp_dir: Path) -> duckdb.DuckDBPyConnection:
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute(f"SET temp_directory='{temp_dir.as_posix()}'")
    con.execute("SET threads=1")
    con.execute("SET preserve_insertion_order=false")
    return con


def _summary(con: duckdb.DuckDBPyConnection, path: Path) -> tuple[int, int, int]:
    """Cheap pass (no text): total rows, distinct act_id, null act_id."""
    row = con.execute(
        """
        SELECT COUNT(*),
               COUNT(DISTINCT act_id),
               COUNT(*) FILTER (WHERE act_id IS NULL)
        FROM read_parquet(?)
        """,
        [path.as_posix()],
    ).fetchone()
    return int(row[0]), int(row[1]), int(row[2])


def _namespace_collisions(
    con: duckdb.DuckDBPyConnection, path: Path
) -> list[NamespaceCollisions]:
    """Per-namespace collision classification (reads + hashes text via spill)."""
    q = """
    WITH base AS (
        SELECT act_id,
               regexp_extract(act_id, '^[A-Za-z]+', 0) AS ns,
               text,
               word_count,
               source_url
        FROM read_parquet(?)
    ),
    grp AS (
        SELECT ns, act_id,
               COUNT(*)                     AS n,
               COUNT(DISTINCT md5(text))    AS ndt,
               COUNT(DISTINCT word_count)   AS ndw,
               COUNT(DISTINCT source_url)   AS ndu
        FROM base
        GROUP BY ns, act_id
        HAVING COUNT(*) > 1
    )
    SELECT ns,
           COUNT(*)                                              AS groups,
           SUM(n)                                                AS "rows",
           SUM(CASE WHEN ndt = 1          THEN 1 ELSE 0 END)     AS all_identical,
           SUM(CASE WHEN ndt = n          THEN 1 ELSE 0 END)     AS all_distinct,
           SUM(CASE WHEN ndt > 1 AND ndt < n THEN 1 ELSE 0 END)  AS "partial",
           SUM(CASE WHEN ndu = 1          THEN 1 ELSE 0 END)     AS same_url,
           SUM(CASE WHEN ndw = 1          THEN 1 ELSE 0 END)     AS same_wordcount,
           MAX(n)                                                AS max_group,
           min(act_id) FILTER (WHERE ndt = 1)                   AS example_identical,
           min(act_id) FILTER (WHERE ndt = n)                   AS example_distinct
    FROM grp
    GROUP BY ns
    ORDER BY "rows" DESC
    """
    out: list[NamespaceCollisions] = []
    for r in con.execute(q, [path.as_posix()]).fetchall():
        out.append(
            NamespaceCollisions(
                namespace=r[0],
                groups=int(r[1]),
                rows=int(r[2]),
                all_identical=int(r[3]),
                all_distinct=int(r[4]),
                partial=int(r[5]),
                same_url=int(r[6]),
                same_wordcount=int(r[7]),
                max_group=int(r[8]),
                example_identical=r[9],
                example_distinct=r[10],
            )
        )
    return out


def analyze_file(
    con: duckdb.DuckDBPyConnection, path: Path
) -> FileCollisions:
    total, distinct, nulls = _summary(con, path)
    fc = FileCollisions(
        name=path.name,
        total_rows=total,
        distinct_ids=distinct,
        null_ids=nulls,
        collision_rows=total - distinct,
    )
    if fc.has_collisions:
        fc.namespaces = _namespace_collisions(con, path)
    return fc


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

# Design conclusions. Embedded here (not hand-edited into the report) so the
# report regenerates verbatim; these are the M0.5A exit deliverable.
STRATEGY_SECTION = """\
## Recommended per-corpus `SourceIdentityStrategy`

The one hard rule (PROPOSAL "First action"): keep `legal_id`, `document_id`, and
`raw_text_hash` orthogonal, and derive `legal_id` from proven source identity
alone. Collisions are represented as data, never uniquified away by a bigger
key. Two identity levels do different jobs:

- **`source_id`** — lossless *row* identity. Must be unique per physical row so
  no source row is dropped.
- **`legal_id`** — *provision* identity. Rows that are the same legal thing
  (segments of one document; ETL duplicates of one section) collapse to one
  `legal_id`. This is where a collision is *resolved*, on evidence, not hidden.

### Statutes & constitutions (USC, all state statutes, constitutions)
`act_id` is unique within the file (M0). No segment problem.
- `source_id = (state, corpus, act_id)` — Tier-1 seed as-is.
- `legal_id = (state, corpus, act_id)`; a text amendment keeps both stable
  (renumber/transfer breaks `act_id` by construction → Tier-3 lineage).

### Federal regulations — `CFR_*` namespace (codified Code of Federal Regulations)
`act_id` is a codified section key (`CFR_T30_P250_S250_420`) and is **nearly
unique** (218,865 of 220,018 rows). The residual collisions are *the same
codified section captured redundantly* — identical `citation` and identical
canonical eCFR `source_url`, some rows byte-identical (ETL dup), some
distinct-length segments of one section.
- `source_id = (state, corpus, act_id, segment_ordinal)` where `segment_ordinal`
  is a stable within-`act_id` index by original row order; add `raw_text_hash`
  as a verification tiebreak.
- `legal_id = (state, corpus, act_id)` at **section** granularity — every
  segment/duplicate of `§ 250.420` maps to one provision.
- Byte-identical rows carry `quality_flags += duplicate_row`; kept for
  losslessness, excluded from `legal_id` cardinality.

### Federal regulations — `FR_*` namespace (Federal Register documents)
`act_id` is a Federal Register **document** number (`FR_RULE_…`,
`FR_PRORULE_…`, `FR_RULE_E…`), not a codified-law key. Nearly every collision
(≈99.99% of `FR` collision groups) is one FR document **split into multiple text
segments** that share all metadata and `source_url`; the dataset provides **no
per-segment discriminator column** (`section_number` = the FR doc number,
constant within the group).
- `source_id = (state, corpus, act_id, segment_ordinal)`; `segment_ordinal` is
  synthesized at ingestion from within-`act_id` row order (dataset has none) and
  verified by `raw_text_hash`.
- `legal_id = (state, corpus, act_id)` at **document** granularity.
- These are *promulgation records*, not codified law: tag
  `document_class = federal_register` vs `codified_cfr` so downstream resolution
  never treats an FR rule document as an in-force CFR section.

### State regulations (IL, KY, MD, ME, MN, OH)
Collisions here are predominantly **literal duplicate rows** (Ohio: 539 of 555
groups fully identical), i.e. upstream ETL duplication rather than segmentation.
- Same `source_id = (state, corpus, act_id, segment_ordinal)` shape.
- `legal_id = (state, corpus, act_id)`; duplicate rows flagged
  `duplicate_row` and collapsed at `legal_id`, genuine multi-segment rows
  preserved as distinct `source_id`s under one `legal_id`.

### Why not simply `(state, corpus, act_id, row_number)`?
That makes every row trivially unique and thereby **hides** the two facts M0.5A
exists to surface: that `FR_*` rows are segments of one document (so a citation
to the document must resolve to a set of segments, not one row) and that
hundreds of groups are literal ETL duplicates (which must be flagged, not minted
as distinct provisions). `segment_ordinal` + `duplicate_row` + document/section
`legal_id` keep the collision *explained and queryable*; a bare row number does
not.
"""


def _pct(num: int, den: int) -> str:
    return f"{100 * num / den:.2f}%" if den else "—"


def render(files: list[FileCollisions], snapshot: str) -> str:
    colliding = [f for f in files if f.has_collisions]
    clean = [f for f in files if not f.has_collisions]
    total_rows = sum(f.total_rows for f in files)
    total_collision_rows = sum(f.collision_rows for f in files)

    L: list[str] = []
    L.append("# M0.5A — Identity-collision analysis")
    L.append("")
    L.append(
        f"Snapshot **{snapshot}** · {len(files)} files scanned · "
        f"{total_rows:,} rows · {total_collision_rows:,} collision rows "
        f"(rows beyond one per distinct `act_id`)."
    )
    L.append("")
    L.append(
        "M0 flagged that `act_id` is 100% populated everywhere but not unique in "
        "the federal regulations file. This report enumerates every corpus where "
        "`act_id` repeats, classifies each collision by *phenomenon* (duplicate "
        "row vs. multi-segment document vs. shared namespace), and only then "
        "recommends a key. **Collisions are entirely a regulations-corpus "
        "phenomenon** — every statute and constitution file has a unique `act_id`."
    )
    L.append("")

    # --- Where collisions live -------------------------------------------
    L.append("## Where `act_id` collides")
    L.append("")
    L.append("| file | rows | distinct `act_id` | null | collision rows | collision % |")
    L.append("|---|--:|--:|--:|--:|--:|")
    for f in sorted(colliding, key=lambda x: -x.collision_rows):
        L.append(
            f"| `{f.name}` | {f.total_rows:,} | {f.distinct_ids:,} | "
            f"{f.null_ids:,} | {f.collision_rows:,} | "
            f"{_pct(f.collision_rows, f.total_rows)} |"
        )
    L.append("")
    L.append(
        f"{len(clean)} of {len(files)} files have a fully unique, non-null "
        "`act_id` (all statutes, constitutions, court rules, guidance, and the "
        "regulations corpora not listed above)."
    )
    L.append("")

    # --- Per-file phenomenon breakdown -----------------------------------
    L.append("## Collision classes (phenomenon before key)")
    L.append("")
    L.append(
        "For each colliding file, grouped by `act_id` namespace (leading prefix). "
        "`text` relationship within a group: **identical** = every row byte-equal "
        "(ETL duplicate rows); **distinct** = every row a different text segment "
        "of one source document; **partial** = a segmented document that also "
        "carries a duplicate. `same url` / `same wc` = groups where `source_url` / "
        "`word_count` never discriminate the rows."
    )
    L.append("")
    for f in sorted(colliding, key=lambda x: -x.collision_rows):
        L.append(f"### `{f.name}`")
        L.append("")
        L.append(
            "| namespace | groups | rows | text identical | text distinct | "
            "partial | same url | same wc | max grp | example (identical / distinct) |"
        )
        L.append("|---|--:|--:|--:|--:|--:|--:|--:|--:|---|")
        for ns in f.namespaces:
            ex_i = f"`{ns.example_identical}`" if ns.example_identical else "—"
            ex_d = f"`{ns.example_distinct}`" if ns.example_distinct else "—"
            L.append(
                f"| `{ns.namespace}` | {ns.groups:,} | {ns.rows:,} | "
                f"{ns.all_identical:,} | {ns.all_distinct:,} | {ns.partial:,} | "
                f"{ns.same_url:,} | {ns.same_wordcount:,} | {ns.max_group} | "
                f"{ex_i} / {ex_d} |"
            )
        L.append("")

    # --- Strategy --------------------------------------------------------
    L.append(STRATEGY_SECTION)
    L.append("")
    L.append("---")
    L.append("")
    L.append(
        "_Generated by `open_us_law_coverage.identity_collisions`. `text` "
        "aggregates run in DuckDB with a hard memory limit + disk spill so the "
        "11 GB federal-regulations `text` column never materializes a whole "
        "row-group._"
    )
    L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="M0.5A identity-collision analysis.")
    ap.add_argument("files", nargs="+", type=Path, help="Parquet file(s) / globs.")
    ap.add_argument("--snapshot", default="v2026.08", help="Snapshot label.")
    ap.add_argument(
        "--out", type=Path, default=Path("reports/M0.5A_identity_collisions.md")
    )
    ap.add_argument(
        "--memory-limit",
        default="5GB",
        help="DuckDB hard memory limit (spills to --temp-dir beyond this).",
    )
    ap.add_argument(
        "--temp-dir",
        type=Path,
        default=Path(".duckdb_spill"),
        help="Directory for DuckDB spill files.",
    )
    args = ap.parse_args()

    paths = sorted({p for g in args.files for p in Path().glob(str(g))} or set(args.files))
    if not paths:
        raise SystemExit("no input files matched")

    con = _connect(args.memory_limit, args.temp_dir)
    results: list[FileCollisions] = []
    for p in paths:
        fc = analyze_file(con, p)
        flag = f"  <-- {fc.collision_rows:,} collision rows" if fc.has_collisions else ""
        print(f"{p.name}: {fc.total_rows:,} rows / {fc.distinct_ids:,} distinct{flag}")
        results.append(fc)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(results, args.snapshot))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
