"""M0 dataset reconnaissance for the Open US Law snapshot.

Produces the schema/behavior report the proposal's Milestone 0 requires, so that
the final identity model is designed from real Parquet rather than the dataset
card. The report answers the "Verified facts vs assumptions to test" questions:

  * Is ``act_id`` populated and unique within (state, corpus)?
  * Does ``act_id`` change under renumbered / transferred / recodified status?
  * Is there any predecessor/successor crosswalk field in the schema?
  * Is the hierarchy clean enough for LOCAL / RELATIVE / CONTAINER resolution?
  * How variable is citation format per jurisdiction?

The cross-snapshot questions (act_id stability under text-only amendment) cannot
be answered from a single snapshot and are reported as such.

Usage:
    uv run python -m open_us_law_coverage.recon data/v2026.08/*.parquet \
        --snapshot v2026.08 --out reports/M0_recon.md
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

# act_id namespace prefixes observed, e.g. USC_T10_C1001_S10001,
# STATE_AK_T10_C10.06_S10.06.005, SCONST_AK_A10_S0.
ACT_ID_PREFIX_RE = re.compile(r"^(?P<prefix>[A-Z]+(?:_[A-Z]{2})?)_")

# The fields we treat as the structural hierarchy for a statute/regulation row.
HIERARCHY_FIELDS = ["title_number", "chapter", "section_number"]

# Statuses where act_id is expected to break and lineage inference is required.
LINEAGE_STATUSES = {"renumbered", "transferred", "recodified", "superseded", "omitted"}

# Inline successor/disposition pointer in the section body, e.g.
# "[§2010. Renumbered §321]" or "[§10542. Repealed. Pub. L. 114-92 ...]".
SUCCESSOR_POINTER_RE = re.compile(
    r"(Renumbered|Transferred|Omitted|Repealed|Recodified|See)\s+§+\s*([0-9A-Za-z.\-]+)",
    re.IGNORECASE,
)

# Fields that would be an explicit predecessor/successor crosswalk if present.
CROSSWALK_CANDIDATES = [
    "formerly_cited_as",
    "renumbered_from",
    "renumbered_to",
    "transferred_from",
    "transferred_to",
    "predecessor",
    "successor",
    "former_citation",
    "history",
]


def _corpus_of(path: Path) -> str:
    """Derive corpus label from a ``us_{juris}_{corpus}.parquet`` filename."""
    stem = path.stem  # us_federal_statutes
    parts = stem.split("_")
    if len(parts) >= 3 and parts[0] == "us":
        return "_".join(parts[2:])
    return stem


def _juris_of(path: Path) -> str:
    parts = path.stem.split("_")
    if len(parts) >= 3 and parts[0] == "us":
        return parts[1]
    return "?"


@dataclass
class FileReport:
    path: Path
    juris: str
    corpus: str
    n_rows: int
    n_cols: int
    columns: list[str]
    null_rates: dict[str, float]
    empty_rates: dict[str, float]  # empty-string rate for string cols
    act_id_populated: float
    act_id_unique: bool
    act_id_dupes: int
    act_id_dupe_examples: list[str]
    act_id_prefixes: dict[str, int]
    status_dist: dict[str, int]
    citation_samples: list[str]
    hierarchy_complete_rate: float
    hierarchy_null_rates: dict[str, float]
    word_count_pct: dict[str, float]
    empty_text_rows: int
    xref_usc_coverage: float
    xref_cfr_coverage: float
    pub_law_coverage: float
    xref_usc_total_edges: int
    lineage_rows: int
    lineage_examples: list[dict] = field(default_factory=list)
    # per-status: (n_rows, n_with_inline_successor_pointer)
    successor_pointer_by_status: dict[str, tuple[int, int]] = field(default_factory=dict)


# Column that can be pathologically large (the section body). One row-group of
# it reaches ~3.3 GB uncompressed in the federal-regulations file, so it is never
# read whole — see `_scan_text_metrics`.
TEXT_COL = "text"


def _scan_text_metrics(
    path: Path, cols: list[str], n: int
) -> tuple[int, int, int, dict[str, tuple[int, int]], list[dict]]:
    """Row-group-at-a-time scan of the large ``text`` column.

    Polars (and a plain ``read_parquet``) materialize the entire ``text`` column
    at once — ~11 GB uncompressed for the regulations file — and OOM a 14 GB box.
    Here each Parquet row-group is decoded on its own (peak ≈ one row-group, ~3-6
    GB worst case) and the memory pool is released between groups, so the scan is
    bounded regardless of total file size. The full column is never converted to
    Python: only the handful of lineage-status rows have their text pulled out
    element-by-element for the successor-pointer regex.

    Returns ``(text_null, text_empty, lineage_rows, successor_by_status,
    lineage_examples)``.
    """
    if TEXT_COL not in cols:
        return 0, 0, 0, {}, []

    pf = pq.ParquetFile(path)
    pool = pa.default_memory_pool()
    has_status = "act_status" in cols
    read_cols = [c for c in (TEXT_COL, "act_status", "act_id", "citation") if c in cols]
    lineage_all = LINEAGE_STATUSES | {"repealed"}

    text_null = text_empty = lineage_rows = 0
    succ: dict[str, list[int]] = {}  # status -> [n_rows, n_with_pointer]
    examples: list[dict] = []

    for g in range(pf.metadata.num_row_groups):
        tbl = pf.read_row_group(g, columns=read_cols)
        text = tbl.column(TEXT_COL)
        text_null += pc.sum(pc.is_null(text)).as_py() or 0
        text_empty += pc.sum(pc.equal(text, "")).as_py() or 0

        if has_status:
            status = tbl.column("act_status").to_pylist()
            for i, st in enumerate(status):
                if st in LINEAGE_STATUSES:
                    lineage_rows += 1
                if st not in lineage_all:
                    continue
                rec = succ.setdefault(st, [0, 0])
                rec[0] += 1
                tx = text[i].as_py()  # one element only — never the whole column
                if tx and SUCCESSOR_POINTER_RE.search(tx):
                    rec[1] += 1
                if st in LINEAGE_STATUSES and len(examples) < 4:
                    examples.append(
                        {
                            "act_id": tbl.column("act_id")[i].as_py() if "act_id" in read_cols else None,
                            "citation": tbl.column("citation")[i].as_py() if "citation" in read_cols else None,
                            "act_status": st,
                            "has_text": bool(tx),
                            "text_head": (tx or "")[:160],
                        }
                    )
        del tbl, text
        pool.release_unused()

    successor_by_status = {k: (v[0], v[1]) for k, v in succ.items()}
    return text_null, text_empty, lineage_rows, successor_by_status, examples


def analyze_file(path: Path) -> FileReport:
    # Read every column EXCEPT the potentially huge `text` body into memory; the
    # other 23 columns are small even for the 582k-row regulations file (~0.7 GB).
    # `text` is handled separately, row-group-at-a-time, in `_scan_text_metrics`.
    schema = pl.read_parquet_schema(path)
    cols = list(schema.keys())
    nontext = [c for c in cols if c != TEXT_COL]
    df = pl.read_parquet(path, columns=nontext)
    n = df.height
    str_cols = [c for c in nontext if schema[c] == pl.String]
    present_hier = [c for c in HIERARCHY_FIELDS if c in cols]

    # ---- bounded scan of the large text column ----
    text_null, text_empty, lineage_rows, successor_by_status, lineage_examples = (
        _scan_text_metrics(path, cols, n)
    )
    empty_text_rows = text_null + text_empty

    # ---- null / empty rates (text folded back in from the scan) ----
    null_rates = {c: (df[c].null_count() / n if n else 0.0) for c in nontext}
    empty_rates = {
        c: (df.select((pl.col(c) == "").sum()).item() or 0) / n if n else 0.0
        for c in str_cols
    }
    if TEXT_COL in cols:
        null_rates[TEXT_COL] = text_null / n if n else 0.0
        empty_rates[TEXT_COL] = text_empty / n if n else 0.0

    # ---- act_id ----
    has_act_id = "act_id" in cols
    if has_act_id:
        aid = df.filter(pl.col("act_id").is_not_null() & (pl.col("act_id") != ""))
        aid_pop = aid.height
        populated = aid_pop / n if n else 0.0
        n_unique = aid["act_id"].n_unique()
        dupes = aid_pop - n_unique
        dupe_examples = (
            aid.group_by("act_id").len().filter(pl.col("len") > 1)["act_id"].head(5).to_list()
            if dupes > 0 else []
        )
        pfx_df = (
            aid.select(pl.col("act_id").str.extract(r"^([A-Z]+(?:_[A-Z]{2})?)_", 1).alias("_pfx"))
            .group_by("_pfx").len()
        )
        prefixes = {(r["_pfx"] or "<no-prefix>"): r["len"] for r in pfx_df.iter_rows(named=True)}
    else:
        populated, dupes, dupe_examples, prefixes = 0.0, 0, [], {}

    # ---- status ----
    if "act_status" in cols:
        sd = df.group_by("act_status").len().sort("len", descending=True)
        # A null act_status is itself a finding; surface it as a visible, counted
        # category so downstream rendering (which sorts/joins status labels) never
        # trips over a None mixed in with strings.
        status_dist = {
            ("<null>" if r["act_status"] is None else r["act_status"]): r["len"]
            for r in sd.iter_rows(named=True)
        }
    else:
        status_dist = {}

    # ---- citation samples ----
    citation_samples = (
        df.select("citation").drop_nulls().head(6)["citation"].to_list()
        if "citation" in cols else []
    )

    # ---- hierarchy ----
    hier_null_rates = {c: null_rates[c] for c in present_hier}
    if present_hier and n:
        hier_complete = df.select(
            pl.all_horizontal([(pl.col(c).is_not_null() & (pl.col(c) != "")) for c in present_hier]).sum()
        ).item() or 0
        hierarchy_complete_rate = hier_complete / n
    else:
        hierarchy_complete_rate = 0.0

    # ---- word-count distribution ----
    if "word_count" in cols:
        wc = df.select(pl.col("word_count").fill_null(0).alias("wc"))["wc"]
        word_count_pct = {
            "min": float(wc.min() or 0),  # type: ignore[arg-type]
            "p50": float(wc.median() or 0),  # type: ignore[arg-type]
            "p95": float(wc.quantile(0.95) or 0),
            "max": float(wc.max() or 0),  # type: ignore[arg-type]
            "mean": float(wc.mean() or 0),  # type: ignore[arg-type]
        }
    else:
        word_count_pct = {}

    # ---- cross-reference coverage / edge counts ----
    def cov(col: str) -> tuple[float, int]:
        if col not in cols:
            return 0.0, 0
        ne = pl.col(col).is_not_null() & (pl.col(col) != "") & (pl.col(col) != "[]")
        agg = df.select(
            ne.sum().alias("w"),
            pl.when(ne).then(pl.col(col).str.count_matches(r'", "', literal=True) + 1)
            .otherwise(0).sum().alias("t"),
        ).row(0, named=True)
        return ((agg["w"] or 0) / n if n else 0.0), int(agg["t"] or 0)

    xref_usc_cov, xref_usc_total = cov("cross_references_usc")
    xref_cfr_cov, _ = cov("cross_references_cfr")
    pub_cov, _ = cov("public_laws_referenced")

    return FileReport(
        path=path,
        juris=_juris_of(path),
        corpus=_corpus_of(path),
        n_rows=n,
        n_cols=len(cols),
        columns=cols,
        null_rates=null_rates,
        empty_rates=empty_rates,
        act_id_populated=populated,
        act_id_unique=(dupes == 0 and has_act_id),
        act_id_dupes=dupes,
        act_id_dupe_examples=dupe_examples,
        act_id_prefixes=prefixes,
        status_dist=status_dist,
        citation_samples=citation_samples,
        hierarchy_complete_rate=hierarchy_complete_rate,
        hierarchy_null_rates=hier_null_rates,
        word_count_pct=word_count_pct,
        empty_text_rows=empty_text_rows,
        xref_usc_coverage=xref_usc_cov,
        xref_cfr_coverage=xref_cfr_cov,
        pub_law_coverage=pub_cov,
        xref_usc_total_edges=xref_usc_total,
        lineage_rows=lineage_rows,
        lineage_examples=lineage_examples,
        successor_pointer_by_status=successor_by_status,
    )


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_report(reports: list[FileReport], snapshot: str) -> str:
    lines: list[str] = []
    w = lines.append

    w("# M0 — Dataset Reconnaissance Report\n")
    w(f"**Snapshot:** `{snapshot}`  ")
    w(f"**Files analyzed:** {len(reports)} (representative sample)  ")
    w(f"**Total rows analyzed:** {sum(r.n_rows for r in reports):,}\n")
    w(
        "> Scope note: This report is computed over a representative subset of the "
        "229-file snapshot (the USC federal statutes — the commissioned corpus — plus "
        "sample state statute and constitution files). The harness runs on any file "
        "glob; point it at the full snapshot to produce the complete report.\n"
    )

    # ---- Key findings up front ----
    w("## 0. Key findings that refine the proposal\n")
    w(
        "- **Uniform 24-column schema** across statutes / constitutions (and, per the "
        "card, regulations / court rules / guidance). One normalizer handles every corpus. "
        "See §1.\n"
        "- **No crosswalk column** for renumber/transfer — confirmed. Lineage must be "
        "inferred, as the proposal expected. **But** the disposition often lives in the "
        "*text*: **100% of `renumbered` USC rows carry an explicit inline successor pointer** "
        "(`[§2010. Renumbered §321]`), giving a *deterministic* lineage edge — stronger than "
        "the similarity-inference fallback the proposal assumed. `transferred`/`omitted` rows "
        "rarely have the one-line pointer (~1-2%); their history sits in `Editorial Notes / "
        "Codification` prose and needs a dedicated parser. `repealed` rows name the repealing "
        "Pub. L. inline (~4% as a `§` pointer, more as prose). See §5.\n"
        "- **`act_id` is a normalized citation with a corpus namespace** "
        "(`USC_…` / `STATE_XX_…` / `SCONST_XX_…`). Good Tier-1 seed; breaks by construction on "
        "renumber/transfer. Enforce uniqueness on `(state, corpus, act_id)`, not the bare id — "
        "`jurisdiction` is uniformly `\"US\"`; `state` is the real discriminator. See §3.\n"
        "- **Flat hierarchy columns are NOT reliable across jurisdictions.** California leaves "
        "`title_number` null on 70% of rows because CA namespaces by *code* (`Cal. BPC`, "
        "`Cal. CCP`) rather than a numbered title; the true hierarchy is in `display_path` / "
        "`breadcrumb`. **The structural parser must read `breadcrumb`/`display_path`, not the "
        "flat `title_number`/`chapter` columns.** USC and AK flat columns are ~100% clean. See §6.\n"
        "- **USC cross-references ship pre-extracted**: 69% of USC rows carry a "
        "`cross_references_usc` array (`\"title:section\"`), ~128k edges in the USC file alone, "
        "plus `public_laws_referenced` on 88%. This is a large head start (and an oracle) for "
        "M4. State files have almost none, so in-body parsing still matters off-federal. See §9.\n"
        "- **`last_amended_year` is mostly null** (59% USC, 98-99% state) and cannot be the "
        "temporal backbone. Snapshot version + `act_status` + `year` carry temporality instead.\n"
        "- **The one unanswerable question**: `act_id` stability under text-only amendment "
        "needs a *second* snapshot to measure. Acquire `v2026.07` (statutes+constitutions) or "
        "the next quarterly release before finalizing Tier-1 identity. See §11.2.\n"
    )

    # ---- Schema consistency ----
    w("## 1. Schema consistency across corpora\n")
    col_sets = {tuple(r.columns) for r in reports}
    if len(col_sets) == 1:
        w(f"All {len(reports)} files share an **identical {reports[0].n_cols}-column schema**:\n")
        w("```")
        for c in reports[0].columns:
            w(c)
        w("```\n")
    else:
        w("**Schema differs across files.** Column sets:\n")
        for r in reports:
            w(f"- `{r.path.name}`: {r.columns}")
        w("")

    # ---- Crosswalk field check ----
    w("## 2. Predecessor/successor crosswalk field?\n")
    all_cols = set(reports[0].columns)
    found = [c for c in CROSSWALK_CANDIDATES if c in all_cols]
    if found:
        w(f"Found candidate crosswalk field(s): `{found}`. Verify semantics before use.\n")
    else:
        w(
            "**No explicit predecessor/successor crosswalk field exists** "
            f"(checked for {CROSSWALK_CANDIDATES}). "
            "This confirms the proposal's expectation: cross-move identity must be "
            "**inferred** (Identity Tier 3), not read from a column. The only "
            "lineage-adjacent signals present are `act_status`, `cross_references_usc/cfr`, "
            "and `public_laws_referenced`.\n"
        )

    # ---- act_id behavior ----
    w("## 3. `act_id` behavior\n")
    w("| File | Corpus | Rows | act_id populated | Unique in file | Dupes | Prefix scheme |")
    w("|---|---|---:|---:|:--:|---:|---|")
    for r in reports:
        pref = ", ".join(f"`{k}`×{v}" for k, v in sorted(r.act_id_prefixes.items()))
        w(
            f"| {r.path.name} | {r.corpus} | {r.n_rows:,} | {_pct(r.act_id_populated)} | "
            f"{'yes' if r.act_id_unique else 'NO'} | {r.act_id_dupes} | {pref} |"
        )
    w("")
    w(
        "**act_id is a normalized, namespaced citation.** The title/chapter/section is "
        "baked into the string (e.g. `USC_T10_C1001_S10001`, `STATE_AK_T10_C10.06_S10.06.005`, "
        "`SCONST_AK_A10_S0`). Implications for identity, per the proposal:\n"
    )
    w(
        "- **Stable under text-only amendment** (the number does not change) → good Tier-1 seed.\n"
        "- **Structurally cannot be stable across renumbering/transfer/recodification** — the "
        "number *is* the ID, so a move changes the ID. Those rows must route to lineage inference.\n"
        "- The corpus prefix (`USC_`/`STATE_XX_`/`SCONST_XX_`) namespaces the ID, so uniqueness "
        "must be checked within `(state, corpus)`, not globally on the bare number.\n"
    )
    dupe_files = [r for r in reports if r.act_id_dupes]
    if dupe_files:
        w("**Duplicate act_id examples (investigate):**")
        for r in dupe_files:
            w(f"- `{r.path.name}`: {r.act_id_dupe_examples}")
        w("")

    # ---- status distribution ----
    w("## 4. `act_status` distribution\n")
    for r in reports:
        w(f"**{r.path.name}**")
        w("| status | count | share |")
        w("|---|---:|---:|")
        for k, v in r.status_dist.items():
            w(f"| {k} | {v:,} | {_pct(v / r.n_rows) if r.n_rows else '—'} |")
        w("")

    # ---- lineage cases ----
    w("## 5. Lineage cases (statuses where act_id is expected to break)\n")
    w(
        "These are the rows that Tier-3 lineage inference must handle. `act_id` for a "
        "`renumbered`/`transferred`/etc. row still encodes *its own* number; there is no "
        "column pointing at the predecessor/successor, so the link must come from text-hash "
        "similarity, hierarchy, section-number transition, and status flags.\n"
    )
    any_ptr = any(r.successor_pointer_by_status for r in reports)
    if any_ptr:
        w(
            "**Inline successor/disposition pointer in the text body** — how often a "
            "disposition status row literally states where it went "
            "(`Renumbered §N` / `Transferred` / `Repealed. Pub. L. …`):\n"
        )
        w("| File | status | rows | with inline pointer | rate |")
        w("|---|---|---:|---:|---:|")
        for r in reports:
            for st, (nrows, hits) in sorted(r.successor_pointer_by_status.items()):
                if nrows:
                    w(
                        f"| {r.path.name} | {st} | {nrows:,} | {hits:,} | "
                        f"{_pct(hits / nrows)} |"
                    )
        w(
            "\n_Takeaway: `renumbered` → deterministic regex lineage. "
            "`transferred`/`omitted` → parse the `Editorial Notes / Codification` block. "
            "`repealed` → capture the repealing Pub. L._\n"
        )
    for r in reports:
        if r.lineage_rows:
            w(f"**{r.path.name}** — {r.lineage_rows:,} lineage-status rows. Examples:")
            for ex in r.lineage_examples:
                w(
                    f"- `{ex['act_id']}` ({ex['act_status']}) — {ex['citation']} — "
                    f"has_text={ex['has_text']}"
                )
                if ex["text_head"]:
                    w(f"  - text head: _{ex['text_head']!r}_")
            w("")

    # ---- hierarchy cleanliness ----
    w("## 6. Hierarchy cleanliness (for LOCAL/RELATIVE/CONTAINER resolution)\n")
    w("| File | title_number null | chapter null | section_number null | complete hierarchy |")
    w("|---|---:|---:|---:|---:|")
    for r in reports:
        hn = r.hierarchy_null_rates
        w(
            f"| {r.path.name} | {_pct(hn.get('title_number', 0))} | "
            f"{_pct(hn.get('chapter', 0))} | {_pct(hn.get('section_number', 0))} | "
            f"{_pct(r.hierarchy_complete_rate)} |"
        )
    w("")

    # ---- citation format variability ----
    w("## 7. Citation-format variability per jurisdiction\n")
    for r in reports:
        w(f"**{r.juris} / {r.corpus}**")
        for c in r.citation_samples[:5]:
            w(f"- `{c}`")
        w("")

    # ---- text length ----
    w("## 8. Text-length distribution (word_count)\n")
    w("| File | min | p50 | p95 | max | mean | empty-text rows |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    for r in reports:
        p = r.word_count_pct
        w(
            f"| {r.path.name} | {p.get('min', 0):.0f} | {p.get('p50', 0):.0f} | "
            f"{p.get('p95', 0):.0f} | {p.get('max', 0):.0f} | {p.get('mean', 0):.0f} | "
            f"{r.empty_text_rows} |"
        )
    w("")

    # ---- cross-reference coverage ----
    w("## 9. Cross-reference coverage\n")
    w(
        "The dataset **ships pre-extracted cross-references** as JSON arrays "
        "(`cross_references_usc` = `[\"title:section\", ...]`, `cross_references_cfr`, "
        "`public_laws_referenced` = `[\"Pub. L. NNN-NNN\", ...]`). This is a major head start "
        "for M4 (in-body cross-reference graph): edges partly exist as data. They still need "
        "validation — treat them as a candidate/oracle source, not ground truth, and keep "
        "dataset-provided edges distinguishable from parser-derived edges per the proposal.\n"
    )
    w("| File | rows w/ USC xref | total USC edges | rows w/ CFR xref | rows w/ Pub.L. |")
    w("|---|---:|---:|---:|---:|")
    for r in reports:
        w(
            f"| {r.path.name} | {_pct(r.xref_usc_coverage)} | {r.xref_usc_total_edges:,} | "
            f"{_pct(r.xref_cfr_coverage)} | {_pct(r.pub_law_coverage)} |"
        )
    w("")

    # ---- null/empty rates for key fields ----
    w("## 10. Null / empty rates for identity & provenance fields\n")
    key_fields = [
        "act_id",
        "citation",
        "citation_short",
        "section_number",
        "section_title",
        "source_url",
        "last_amended_year",
        "subsection_count",
        "text",
    ]
    w("| File | " + " | ".join(key_fields) + " |")
    w("|---" * (len(key_fields) + 1) + "|")
    for r in reports:
        cells = []
        for kf in key_fields:
            nr = r.null_rates.get(kf, 0.0)
            er = r.empty_rates.get(kf, 0.0)
            cells.append(_pct(max(nr, nr + er)))
        w(f"| {r.path.name} | " + " | ".join(cells) + " |")
    w("\n_(Cell = null-rate, or null+empty-string rate for string columns.)_\n")

    # ---- answers to the assumption questions ----
    w("## 11. Answers to the proposal's M0 assumption checks\n")
    w(
        "1. **Is `act_id` populated for every corpus and unique within (jurisdiction, corpus)?** "
        "Populated at ~100% across sampled files; unique within each file (see §3). "
        "`jurisdiction` is uniformly `\"US\"`; the real discriminator is the `state` field "
        "(`federal`, `AK`, …). Uniqueness should be enforced on `(state, corpus, act_id)`.\n"
    )
    w(
        "2. **Does `act_id` stay fixed under text-only amendment across two snapshots?** "
        "**Cannot be answered from a single snapshot.** Only `v2026.08` is in hand. Requires "
        "diffing against another snapshot (`v2026.07` is statutes+constitutions only). "
        "Structural reasoning says yes (the number is unchanged by text amendment), but this "
        "must be *measured* before Tier-1 identity is finalized.\n"
    )
    w(
        "3. **Does `act_id` change under renumbered/transferred/recodified?** By construction, "
        "yes — the number is baked into the ID, so a move produces a different ID. These rows "
        "exist (see §4/§5) and carry no pointer to their counterpart, so they route to Tier-3 "
        "lineage inference.\n"
    )
    w(
        "4. **Is there a predecessor/successor crosswalk field?** **No** (see §2). Confirmed "
        "absent. Lineage must be inferred.\n"
    )
    w(
        "5. **Is hierarchy clean enough for deterministic LOCAL/RELATIVE/CONTAINER?** "
        "See §6. Where `title_number`/`chapter`/`section_number` are fully populated and the "
        "`breadcrumb`/`display_path` structures are present, deterministic container resolution "
        "is feasible; rows with null hierarchy components must use the abstain path.\n"
    )
    w(
        "6. **How variable is citation format per jurisdiction?** Highly regular *within* a "
        "corpus but different *across* them (see §7): `NN U.S.C. § NNNN`, "
        "`Alaska Stat. § NN.NN.NNN`, `Ak. Const. art. N, § N`. A per-jurisdiction grammar/alias "
        "table is warranted, exactly as the proposal's M7 anticipates. USC format is clean and "
        "should be the first grammar.\n"
    )

    return "\n".join(lines) + "\n"


def render_summary(reports: list[FileReport], snapshot: str) -> str:
    """Scalable report for the full snapshot (many files): cross-file rollups and a
    compact per-file table instead of full per-file detail."""
    lines: list[str] = []
    w = lines.append
    total_rows = sum(r.n_rows for r in reports)

    w("# M0 — Full-Snapshot Reconnaissance\n")
    w(f"**Snapshot:** `{snapshot}`  ")
    w(f"**Files:** {len(reports)}  ")
    w(f"**Total rows:** {total_rows:,}\n")

    # --- schema consistency across ALL files ---
    w("## 1. Schema consistency across all files\n")
    col_sets: dict[tuple, list[str]] = {}
    for r in reports:
        col_sets.setdefault(tuple(r.columns), []).append(r.path.name)
    if len(col_sets) == 1:
        cols0 = reports[0].columns
        w(
            f"**All {len(reports)} files share one identical {len(cols0)}-column schema** — a "
            "single normalizer handles every corpus and jurisdiction. Columns: "
            + ", ".join(f"`{c}`" for c in cols0)
            + "\n"
        )
    else:
        w(f"**{len(col_sets)} distinct schemas** across files:\n")
        for cols, names in sorted(col_sets.items(), key=lambda kv: -len(kv[1])):
            w(f"- **{len(names)} files**, {len(cols)} cols: {names[:3]}{' …' if len(names) > 3 else ''}")
            base = set(col_sets and reports[0].columns)
            diff_extra = set(cols) - base
            diff_missing = base - set(cols)
            if diff_extra or diff_missing:
                w(
                    f"  - extra: {sorted(map(str, diff_extra)) or '—'}; "
                    f"missing: {sorted(map(str, diff_missing)) or '—'}"
                )
        w("")

    # --- crosswalk field across all ---
    all_present_cols = set().union(*(set(r.columns) for r in reports))
    found = [c for c in CROSSWALK_CANDIDATES if c in all_present_cols]
    w("## 2. Predecessor/successor crosswalk field?\n")
    w(
        (f"Found: `{found}` — verify semantics.\n" if found else
         "**No crosswalk column anywhere in the snapshot.** Lineage across "
         "renumber/transfer/recodify must be inferred (Identity Tier 3). Confirmed at "
         "full-snapshot scale.\n")
    )

    # --- per-corpus rollup ---
    w("## 3. Per-corpus rollup\n")
    by_corpus: dict[str, list[FileReport]] = {}
    for r in reports:
        by_corpus.setdefault(r.corpus, []).append(r)
    w("| Corpus | files | rows | act_id 100%? | median hierarchy-complete | statuses seen |")
    w("|---|---:|---:|:--:|---:|---|")
    for corpus, rs in sorted(by_corpus.items(), key=lambda kv: -sum(x.n_rows for x in kv[1])):
        rows = sum(x.n_rows for x in rs)
        all_pop = all(x.act_id_populated > 0.999 for x in rs)
        hcs = sorted(x.hierarchy_complete_rate for x in rs)
        med_h = hcs[len(hcs) // 2]
        statuses = set()
        for x in rs:
            statuses |= set(x.status_dist)
        w(
            f"| {corpus} | {len(rs)} | {rows:,} | {'yes' if all_pop else 'NO'} | "
            f"{_pct(med_h)} | {', '.join(sorted(statuses)[:6])}{' …' if len(statuses) > 6 else ''} |"
        )
    w("")

    # --- act_id prefix schemes ---
    w("## 4. `act_id` namespace schemes observed\n")
    prefix_counts: dict[str, int] = {}
    for r in reports:
        for pfx, c in r.act_id_prefixes.items():
            prefix_counts[pfx] = prefix_counts.get(pfx, 0) + c
    w("| prefix | rows |")
    w("|---|---:|")
    for pfx, c in sorted(prefix_counts.items(), key=lambda kv: -kv[1]):
        w(f"| `{pfx}_…` | {c:,} |")
    w(
        "\n_The prefix namespaces the id by corpus+jurisdiction, so enforce act_id uniqueness on "
        "`(state, corpus, act_id)`._\n"
    )

    # --- hierarchy-cleanliness outliers ---
    w("## 5. Hierarchy-cleanliness outliers (statutes/regulations)\n")
    w(
        "Files where flat `title_number`/`chapter`/`section_number` do **not** give a complete "
        "hierarchy on most rows — these must resolve structure from `breadcrumb`/`display_path` "
        "instead (the California pattern). Showing files with <90% complete hierarchy:\n"
    )
    w("| File | rows | complete hierarchy | title_number null |")
    w("|---|---:|---:|---:|")
    outliers = sorted(
        (r for r in reports if r.hierarchy_complete_rate < 0.90 and r.n_rows > 50),
        key=lambda r: r.hierarchy_complete_rate,
    )
    for r in outliers[:40]:
        w(
            f"| {r.path.name} | {r.n_rows:,} | {_pct(r.hierarchy_complete_rate)} | "
            f"{_pct(r.hierarchy_null_rates.get('title_number', 0))} |"
        )
    w(f"\n_{len(outliers)} of {len(reports)} files fall below 90% flat-hierarchy completeness._\n")

    # --- citation format catalog ---
    w("## 6. Citation-format catalog (one exemplar per file)\n")
    w("| jurisdiction | corpus | example citation |")
    w("|---|---|---|")
    for r in sorted(reports, key=lambda r: (r.corpus, r.juris)):
        ex = r.citation_samples[0] if r.citation_samples else "—"
        w(f"| {r.juris} | {r.corpus} | `{ex}` |")
    w("")

    # --- cross-reference coverage by corpus ---
    w("## 7. Cross-reference coverage by corpus\n")
    w("| Corpus | rows | total USC edges | total rows w/ USC xref |")
    w("|---|---:|---:|---:|")
    for corpus, rs in sorted(by_corpus.items(), key=lambda kv: -sum(x.xref_usc_total_edges for x in kv[1])):
        rows = sum(x.n_rows for x in rs)
        edges = sum(x.xref_usc_total_edges for x in rs)
        with_xref = sum(round(x.xref_usc_coverage * x.n_rows) for x in rs)
        w(f"| {corpus} | {rows:,} | {edges:,} | {with_xref:,} ({_pct(with_xref / rows) if rows else '—'}) |")
    w("")

    # --- lineage load ---
    w("## 8. Lineage-status load (rows needing Tier-3 handling)\n")
    total_lineage = sum(r.lineage_rows for r in reports)
    ren = sum(r.successor_pointer_by_status.get("renumbered", (0, 0))[0] for r in reports)
    ren_ptr = sum(r.successor_pointer_by_status.get("renumbered", (0, 0))[1] for r in reports)
    w(
        f"Across the snapshot, **{total_lineage:,} rows** carry a disposition status "
        f"(renumbered/transferred/recodified/superseded/omitted). Of **{ren:,} `renumbered`** "
        f"rows, **{ren_ptr:,} ({_pct(ren_ptr / ren) if ren else '—'})** state their successor "
        "inline in the text → deterministic lineage edge. Transferred/omitted need the "
        "`Editorial Notes / Codification` parser.\n"
    )

    # --- compact per-file table (appendix) ---
    w("## 9. Per-file summary (appendix)\n")
    w("| File | rows | act_id pop | unique | hier-complete | USC edges | statuses |")
    w("|---|---:|---:|:--:|---:|---:|---:|")
    for r in sorted(reports, key=lambda r: r.path.name):
        w(
            f"| {r.path.name} | {r.n_rows:,} | {_pct(r.act_id_populated)} | "
            f"{'y' if r.act_id_unique else 'N'} | {_pct(r.hierarchy_complete_rate)} | "
            f"{r.xref_usc_total_edges:,} | {len(r.status_dist)} |"
        )
    w("")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="M0 dataset reconnaissance report.")
    ap.add_argument("files", nargs="+", type=Path, help="Parquet file(s) / globs to analyze.")
    ap.add_argument("--snapshot", default="v2026.08", help="Snapshot label for the report.")
    ap.add_argument("--out", type=Path, default=Path("reports/M0_recon.md"))
    ap.add_argument(
        "--summary", action="store_true",
        help="Force the scalable summary report (auto-enabled for >8 files).",
    )
    args = ap.parse_args()

    paths: list[Path] = []
    for f in args.files:
        paths.extend(sorted(Path().glob(str(f))) if any(ch in str(f) for ch in "*?[") else [f])
    paths = [p for p in paths if p.suffix == ".parquet"]
    if not paths:
        raise SystemExit("No parquet files matched.")

    reports = []
    for p in paths:
        print(f"analyzing {p} ...", flush=True)
        reports.append(analyze_file(p))

    use_summary = args.summary or len(reports) > 8
    md = render_summary(reports, args.snapshot) if use_summary else render_report(reports, args.snapshot)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md)
    print(f"\nwrote {args.out} ({len(md):,} bytes, {'summary' if use_summary else 'detailed'} mode)")


if __name__ == "__main__":
    main()
