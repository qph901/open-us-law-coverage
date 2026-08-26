"""M0.5A.1 — collision-provenance + segment-order spike.

M0.5A established *that* ``act_id`` collides (entirely in regulations corpora)
and classified each collision group by text relationship (duplicate / segmented /
partial). It hypothesized that the distinct-text ``FR_*`` collisions were "one
Federal Register document split into multiple ordered segments." M0.5A.1 tests
that hypothesis and the ordinal it implies — and **finds it largely wrong**.

PROPOSAL.md framed A.1 as a v2026.07 <-> v2026.08 comparison. That comparison has
an **empty domain**: regulations were *introduced* in v2026.08 (HF commit
``2806c009c55c`` "v2026.08: add regulations, court rules, agency guidance"); the
v2026.07 snapshot contains **zero** regulations files, and every colliding
``act_id`` lives in a regulations file. So exit questions 1, 2, and the
"dataset-defined vs. snapshot-observed" half of 4 are **not testable** with the
snapshots that exist — the honest answer is *evidence unavailable*, to revisit
when a second regulations-bearing snapshot ships.

What it measures within v2026.08, per colliding file and ``act_id`` namespace:

  * **Phenomenon** (recomputed, self-contained): per collision group, are the row
    texts all identical (ETL duplicate), all distinct (segmented?), or partial.
  * **Physical contiguity**: using DuckDB ``file_row_number``, is a group's set of
    rows an adjacent block (``max(frn)-min(frn) == n-1``)? True ordered segments
    of one document would be written adjacently; scattered rows are not.
  * **Source-defined ordinal?**: does *any* structural column
    (``section_number``, ``display_path``, ``breadcrumb``, ``citation``,
    ``subsection_count``) vary within a group and so could order/name its
    segments? Where none does, no ordinal can be read from the data.
  * **Segment relationship (sampled)**: for a deterministic sample of distinct-text
    groups, order the rows by ``frn`` and test whether they are *pieces of one
    document* or *co-numbered distinct documents*. Signals: the **continuation
    rate** (fraction of internal seams where the next row starts lowercase — a
    true mid-sentence continuation) and the **shared-preamble rate** (fraction of
    groups where every row restarts with the same leading text, e.g. the agency
    header). Near-zero continuation + high shared-preamble ⇒ co-numbered distinct
    documents, **not** ordered segments; concatenation reconstructs nothing.

Memory: ``us_federal_regulations.parquet`` has an ~11 GB ``text`` column with a
single 3.3 GB row-group; pyarrow ``read_row_group`` / polars both materialize a
whole row-group and OOM the box (see CLAUDE.md). All ``text`` work here runs in
DuckDB with a hard ``memory_limit`` + disk spill, which streams the column in
vectors — never holding a row-group. Keep it that way.

Usage:
    uv run python -m open_us_law_coverage.segment_provenance \
        data/v2026.08_full/*_regulations.parquet --snapshot v2026.08 \
        --out reports/M0.5A1_segment_provenance.md \
        --memory-limit 4GB --temp-dir /path/to/scratch/ddspill
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import duckdb

# Structural columns that could, in principle, name or order the segments of one
# act_id. word_count / source_url are excluded on purpose: word_count is derived
# from text (varies iff text varies, so it is not independent evidence of an
# ordinal), and source_url is the document locator, constant across a document's
# segments. These five are the only columns that could carry a *source-defined*
# discriminator.
STRUCT_COLS = ["section_number", "display_path", "breadcrumb", "citation", "subsection_count"]

# Segment-relationship probe: sample size per file/namespace (deterministic, by
# act_id) and the leading-character window used to detect a shared preamble.
SAMPLE_GROUPS = 300
HEAD_LEN = 30


@dataclass
class Segment:
    frn: int
    h: str
    struct: tuple  # values of STRUCT_COLS, for within-group distinct counting


@dataclass
class NamespaceProvenance:
    namespace: str
    groups: int = 0
    rows: int = 0
    # phenomenon
    all_identical: int = 0
    all_distinct: int = 0
    partial: int = 0
    # order/adjacency
    contiguous: int = 0                 # rows form an adjacent physical block
    distinct_contiguous: int = 0        # distinct-text AND adjacent
    identical_scattered: int = 0        # identical-text AND NOT adjacent -> dup re-emission
    # ordinal source
    has_struct_discriminator: int = 0   # some STRUCT col varies within the group
    distinct_no_ordinal: int = 0        # distinct-text groups w/ NO structural discriminator
    # segment-relationship sample (filled later)
    sample_groups: int = 0
    sample_shared_head: int = 0         # groups where every row shares the leading HEAD_LEN chars
    sample_seams: int = 0
    sample_continuation: int = 0        # seams where the next row starts lowercase


@dataclass
class FileProvenance:
    name: str
    namespaces: dict[str, NamespaceProvenance] = field(default_factory=dict)
    sampled: int = 0

    @property
    def total_groups(self) -> int:
        return sum(n.groups for n in self.namespaces.values())


def _connect(memory_limit: str, temp_dir: Path) -> duckdb.DuckDBPyConnection:
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute(f"SET temp_directory='{temp_dir.as_posix()}'")
    con.execute("SET threads=1")
    con.execute("SET preserve_insertion_order=true")  # keep file order for frn/text pulls
    return con


def _colliding_rows(con: duckdb.DuckDBPyConnection, path: Path):
    """Per-row (frn, act_id, ns, text-hash, structural cols) for colliding act_ids
    only. md5(text) streams over the whole file; only colliding rows return."""
    struct_sel = ", ".join(STRUCT_COLS)
    q = f"""
    WITH b AS (
        SELECT file_row_number AS frn,
               act_id,
               regexp_extract(act_id, '^[A-Za-z]+', 0) AS ns,
               md5(text) AS h,
               {struct_sel}
        FROM read_parquet(?, file_row_number=true)
    ),
    dup AS (SELECT act_id FROM b GROUP BY act_id HAVING COUNT(*) > 1)
    SELECT b.* FROM b SEMI JOIN dup USING (act_id)
    ORDER BY b.ns, b.act_id, b.frn
    """
    return con.execute(q, [path.as_posix()]).fetchall()


def _analyze_groups(rows) -> tuple[dict[str, NamespaceProvenance], dict[str, list[str]]]:
    """Group colliding rows by (ns, act_id) in physical order; classify each and
    collect distinct-text groups (any adjacency) as segment-relationship candidates."""
    by_group: dict[tuple[str, str], list[Segment]] = defaultdict(list)
    for r in rows:
        frn, act_id, ns, h = r[0], r[1], r[2], r[3]
        struct = tuple(r[4 : 4 + len(STRUCT_COLS)])
        by_group[(ns, act_id)].append(Segment(int(frn), h, struct))

    nss: dict[str, NamespaceProvenance] = {}
    distinct_candidates: dict[str, list[str]] = defaultdict(list)  # ns -> act_ids

    for (ns, act_id), segs in by_group.items():
        segs.sort(key=lambda s: s.frn)
        n = len(segs)
        npr = nss.setdefault(ns, NamespaceProvenance(namespace=ns))
        npr.groups += 1
        npr.rows += n

        ndh = len({s.h for s in segs})
        all_identical = ndh == 1
        all_distinct = ndh == n
        if all_identical:
            npr.all_identical += 1
        elif all_distinct:
            npr.all_distinct += 1
        else:
            npr.partial += 1

        span = segs[-1].frn - segs[0].frn
        contiguous = span == n - 1
        if contiguous:
            npr.contiguous += 1
        if all_distinct:
            distinct_candidates[ns].append(act_id)
            if contiguous:
                npr.distinct_contiguous += 1
        if all_identical and not contiguous:
            npr.identical_scattered += 1

        has_disc = any(
            len({s.struct[i] for s in segs}) > 1 for i in range(len(STRUCT_COLS))
        )
        if has_disc:
            npr.has_struct_discriminator += 1
        if all_distinct and not has_disc:
            npr.distinct_no_ordinal += 1

    return nss, distinct_candidates


def _segment_relationship_sample(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    ns_to_act_ids: dict[str, list[str]],
    nss: dict[str, NamespaceProvenance],
) -> int:
    """For a deterministic sample of distinct-text groups per namespace, pull the
    rows' text ordered by frn and measure whether they are pieces of one document
    (mid-sentence continuations) or co-numbered distinct documents (each restarts
    with a shared preamble)."""
    sampled: list[str] = []
    for act_ids in ns_to_act_ids.values():
        sampled.extend(sorted(act_ids)[:SAMPLE_GROUPS])
    if not sampled:
        return 0

    placeholders = ", ".join("?" for _ in sampled)
    q = f"""
    SELECT regexp_extract(act_id, '^[A-Za-z]+', 0) AS ns, act_id,
           file_row_number AS frn, text
    FROM read_parquet(?, file_row_number=true)
    WHERE act_id IN ({placeholders})
    ORDER BY ns, act_id, frn
    """
    rows = con.execute(q, [path.as_posix(), *sampled]).fetchall()

    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for ns, act_id, _frn, text in rows:
        groups[(ns, act_id)].append(text or "")

    for (ns, _act_id), texts in groups.items():
        npr = nss[ns]
        npr.sample_groups += 1
        heads = {t.lstrip()[:HEAD_LEN] for t in texts}
        if len(heads) == 1:
            npr.sample_shared_head += 1
        for prev, nxt in zip(texts, texts[1:]):
            npr.sample_seams += 1
            q_ = nxt.lstrip()
            if q_ and q_[0].islower():
                npr.sample_continuation += 1
    return len(sampled)


def analyze_file(con: duckdb.DuckDBPyConnection, path: Path) -> FileProvenance:
    rows = _colliding_rows(con, path)
    fp = FileProvenance(name=path.name)
    if not rows:
        return fp
    nss, distinct_candidates = _analyze_groups(rows)
    fp.namespaces = nss
    fp.sampled = _segment_relationship_sample(con, path, distinct_candidates, nss)
    return fp


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

# The five exit questions and their evidence-bounded answers, plus the one finding
# that revises M0.5A. Embedded (not hand-edited into the report) so the report
# regenerates verbatim; the numeric tables below supply the evidence. Prose is
# kept qualitative so it never drifts from the computed figures.
EXIT_SECTION = """\
## Two findings that reshape M0.5A

**1. The cross-snapshot premise is empty.** PROPOSAL.md scoped A.1 as a comparison
of each multi-row `act_id` **shared between v2026.07 and v2026.08**. That set is
empty. Regulations — the *only* corpora where `act_id` collides — were
**introduced in v2026.08** (HF dataset commit `2806c009c55c`, "v2026.08: add
regulations, court rules, agency guidance and federal materials"). v2026.07 holds
**0 of 17** regulations files and **none** of the 7 colliding files. There is no
prior observation of any segment, so segment membership and row order across
snapshots **cannot be tested yet** — not "were tested and found stable." Re-run
when a second regulations-bearing snapshot (v2026.09+) ships; this is a standing
correctness dependency.

**2. `FR_*` distinct-text collisions are co-numbered distinct documents, not
ordered segments.** M0.5A read the 165,044 distinct-text `FR` groups as "one
Federal Register document split into multiple text segments." The single-snapshot
evidence contradicts that: their rows are **physically scattered** (essentially
none are an adjacent block), the segment-relationship sample finds a **continuation
rate of essentially zero** (no seam continues mid-sentence into the next row), and
**almost every group's rows restart with the same agency preamble**. These are
co-numbered captures under one Federal-Register document number — each row a
self-contained document — so concatenating them "in order" reconstructs nothing.
`CFR_*` is genuinely mixed (a minority of seams are true continuations), i.e. some
real section-segmentation plus duplicates. The corrected identity consequence is
below.

## The five exit questions

1. **Is segment membership stable across the two snapshots?**
   *Evidence unavailable.* Regulations exist in exactly one snapshot; no
   cross-snapshot comparison is possible. Do not assume stability.

2. **Is observed row order stable across snapshots?**
   *Evidence unavailable*, same reason. Row order is well-defined *within*
   v2026.08 (Parquet preserves physical row order on read), but its persistence
   across a regeneration is unobserved.

3. **Does observed row order correspond to coherent reading order?**
   *No for `FR_*`; partly for `CFR_*`.* `FR` co-numbered rows are not pieces of one
   linear document (continuation rate ≈ 0, shared preamble ≈ all), so there is no
   reading order to honor. `CFR` shows a minority of genuine mid-sentence
   continuations, so *some* CFR groups are truly segmented; even there the rows are
   not physically adjacent, so order rests on physical row number alone.

4. **Is an ordinal source-defined, dataset-defined, or merely snapshot-observed?**
   *At best snapshot-observed.* For the large majority of distinct-text groups
   **no structural column** (`section_number`, `display_path`, `breadcrumb`,
   `citation`, `subsection_count`) varies within the group, so the dataset offers
   **no source-defined ordinal**; the only ordering signal is physical row order,
   whose cross-snapshot stability is (per 1–2) untested. `segment_ordinal` is thus
   a *snapshot-observed* index — never source- or dataset-guaranteed.

5. **Can we assign source identity without pretending we know more than the
   evidence establishes?**
   *Yes.* Emit `segment_ordinal` from physical row order tagged
   `segment_order_method = physical_row_order`,
   `segment_order_confidence = snapshot_observed`; keep `raw_text_hash` as the
   content tiebreak; flag byte-identical rows `duplicate_row`; collapse to
   `legal_id = (state, corpus, act_id)`. Crucially, do **not** treat the ordinal as
   a reading order: for `FR_*` the co-numbered rows are alternative/self-contained
   captures, so full-text reconstruction by concatenation is invalid, not merely
   "best-effort."

## Corrected consequence for the source-identity contract

The M0.5A *keys* stand; its *rationale for `FR_*`* is corrected. Restate the FR
clause as: `act_id` is a Federal-Register **document number** under which the
dataset may store **several co-numbered, self-contained rows** (distinct captures,
differing lengths, each restarting with the agency preamble) — **not** ordered
segments of one text. Therefore:

- `source_id = (state, corpus, act_id, segment_ordinal)`; `segment_ordinal` is
  snapshot-observed physical row order, a lossless *row* discriminator only.
- `legal_id = (state, corpus, act_id)` still collapses co-numbered rows to one
  Federal-Register document entity, but that entity's text is a **set of
  alternative captures**, never a concatenation.
- `document_class = federal_register` (promulgation record) keeps FR OFF for
  operative-law resolution, which is what makes the unresolved segmentation
  tolerable.
- Nothing durable may depend on a particular ordinal value surviving a
  regeneration; recompute and re-measure at every new snapshot.
"""


def _pct(num: int, den: int) -> str:
    return f"{100 * num / den:.1f}%" if den else "—"


def render(files: list[FileProvenance], snapshot: str) -> str:
    active = [f for f in files if f.total_groups > 0]

    L: list[str] = []
    L.append("# M0.5A.1 — Collision-provenance + segment-order spike")
    L.append("")
    total_groups = sum(f.total_groups for f in active)
    L.append(
        f"Snapshot **{snapshot}** · {len(active)} colliding regulations files · "
        f"{total_groups:,} collision groups analyzed. Segment ordering is examined "
        "from physical row order (`file_row_number`); all `text` work streams "
        "through DuckDB with a hard memory limit + disk spill."
    )
    L.append("")
    L.append(EXIT_SECTION)
    L.append("")

    # --- Evidence table: phenomenon x adjacency x ordinal ----------------
    L.append("## Evidence (per file / `act_id` namespace)")
    L.append("")
    L.append(
        "**ident. / dist. / part.** = text relationship within the group. "
        "**contig.** = rows form an adjacent physical block. **dist.+contig.** = "
        "distinct-text *and* adjacent. **ident.+scatter** = identical-text *and* "
        "non-adjacent → duplicate re-emission, not a segment. **struct. discr.** = "
        "some structural column varies within the group. **dist. no-ordinal** = "
        "distinct-text groups with **no** structural column to order them."
    )
    L.append("")
    L.append(
        "| file | ns | groups | ident. | dist. | part. | contig. | dist.+contig. | "
        "ident.+scatter | struct. discr. | dist. no-ordinal |"
    )
    L.append("|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|")
    for f in sorted(active, key=lambda x: -x.total_groups):
        for ns in sorted(f.namespaces.values(), key=lambda n: -n.groups):
            L.append(
                f"| `{f.name}` | `{ns.namespace}` | {ns.groups:,} | "
                f"{ns.all_identical:,} | {ns.all_distinct:,} | {ns.partial:,} | "
                f"{ns.contiguous:,} | {ns.distinct_contiguous:,} | "
                f"{ns.identical_scattered:,} | {ns.has_struct_discriminator:,} | "
                f"{ns.distinct_no_ordinal:,} |"
            )
    L.append("")

    # --- Segment-relationship sample -------------------------------------
    L.append("## Segment relationship (sampled distinct-text groups)")
    L.append("")
    L.append(
        f"For up to {SAMPLE_GROUPS} distinct-text groups per file/namespace (chosen "
        "deterministically by `act_id`), rows are ordered by `file_row_number`. "
        "**continuation rate** = share of internal seams where the next row starts "
        "lowercase (a true mid-sentence continuation of one document). "
        f"**shared-preamble rate** = share of groups whose rows all restart with the "
        f"same leading {HEAD_LEN} characters (e.g. an agency header). Low "
        "continuation + high shared-preamble ⇒ co-numbered distinct documents, not "
        "ordered segments."
    )
    L.append("")
    L.append(
        "| file | ns | sampled groups | seams | continuation rate | shared-preamble rate |"
    )
    L.append("|---|---|--:|--:|--:|--:|")
    for f in sorted(active, key=lambda x: -x.total_groups):
        for ns in sorted(f.namespaces.values(), key=lambda n: -n.groups):
            if ns.sample_groups == 0:
                continue
            L.append(
                f"| `{f.name}` | `{ns.namespace}` | {ns.sample_groups:,} | "
                f"{ns.sample_seams:,} | {_pct(ns.sample_continuation, ns.sample_seams)} | "
                f"{_pct(ns.sample_shared_head, ns.sample_groups)} |"
            )
    L.append("")
    L.append("---")
    L.append("")
    L.append(
        "_Generated by `open_us_law_coverage.segment_provenance`. Cross-snapshot "
        "questions (1, 2, and the stability half of 4) are unanswerable until a "
        "second regulations-bearing snapshot exists; re-run then. `text` "
        "aggregates stream in DuckDB under a hard memory limit + disk spill so the "
        "11 GB federal-regulations `text` column never materializes a whole "
        "row-group._"
    )
    L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser(description="M0.5A.1 collision-provenance + segment-order spike.")
    ap.add_argument("files", nargs="+", type=Path, help="Parquet file(s) / globs.")
    ap.add_argument("--snapshot", default="v2026.08", help="Snapshot label.")
    ap.add_argument("--out", type=Path, default=Path("reports/M0.5A1_segment_provenance.md"))
    ap.add_argument("--memory-limit", default="4GB",
                    help="DuckDB hard memory limit (spills to --temp-dir beyond this).")
    ap.add_argument("--temp-dir", type=Path, default=Path(".duckdb_spill"),
                    help="Directory for DuckDB spill files.")
    args = ap.parse_args()

    paths = sorted({p for g in args.files for p in Path().glob(str(g))} or set(args.files))
    if not paths:
        raise SystemExit("no input files matched")

    con = _connect(args.memory_limit, args.temp_dir)
    results: list[FileProvenance] = []
    for p in paths:
        fp = analyze_file(con, p)
        if fp.total_groups:
            print(f"{p.name}: {fp.total_groups:,} collision groups, "
                  f"{fp.sampled:,} sampled for segment-relationship")
        else:
            print(f"{p.name}: no collisions")
        results.append(fp)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(results, args.snapshot))
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
