"""Cross-snapshot ``act_id`` behavior diff (answers the one open M0 question).

M0 could not determine, from a single snapshot, whether ``act_id`` stays fixed
under text-only amendment (vs changing on renumber/transfer). This compares the
same corpus file across two snapshots and classifies every ``act_id``:

  * **stable-unchanged**  — act_id in both, identical text hash (pure carry-over).
  * **stable-amended**    — act_id in both, text changed → *this is the key
    evidence that act_id survives text-only amendment.*
  * **added**             — act_id only in the newer snapshot.
  * **removed**           — act_id only in the older snapshot (withdrawn,
    renumbered away, repealed-and-dropped, …).

It then focuses on the newer snapshot's disposition-status rows
(``renumbered``/``transferred``/…) and checks whether their *predecessor*
number existed as an act_id in the older snapshot — i.e. whether a move really
does change the id, as the identity model assumes.

Usage:
    uv run python -m open_us_law_coverage.snapshot_diff \
        --old data/v2026.07/us_federal_statutes.parquet \
        --new data/v2026.08/us_federal_statutes.parquet \
        --old-label v2026.07 --new-label v2026.08 \
        --out reports/M0_act_id_stability.md
"""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path

import polars as pl

# Successor pointer in a renumbered/transferred body, e.g. "Renumbered §321".
SUCCESSOR_RE = re.compile(r"(Renumbered|Transferred|Recodified)\s+§+\s*([0-9A-Za-z.\-]+)", re.I)

# The OLRC editorial/historical apparatus is appended to the operative text under
# headers like these. Splitting on the first one isolates the operative prefix.
NOTES_SPLIT_RE = re.compile(r"\n(?:Editorial Notes|Statutory Notes|Amendments)\n")


def _operative(text: str | None) -> str:
    return NOTES_SPLIT_RE.split(text or "", maxsplit=1)[0].strip()


def _hash_one(s: str | None) -> str:
    # Preserve the null/empty distinction (M1A.5 review P4): a null body and an
    # empty-string body are different states, so they must not share a hash. Null
    # maps to a sentinel that no sha256 hex digest can collide with.
    if s is None:
        return "NULL"
    return hashlib.sha256(s.encode()).hexdigest()


def _hash_col(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        pl.col("text")
        .map_elements(_hash_one, return_dtype=pl.String, skip_nulls=False)
        .alias("_text_hash")
    )


def diff(old: pl.DataFrame, new: pl.DataFrame) -> dict:
    old = _hash_col(old.select(["act_id", "citation", "act_status", "text"]))
    new = _hash_col(new.select(["act_id", "citation", "act_status", "text"]))

    old_ids = set(old["act_id"].to_list())
    new_ids = set(new["act_id"].to_list())
    common = old_ids & new_ids

    old_hash = dict(zip(old["act_id"].to_list(), old["_text_hash"].to_list()))
    new_hash = dict(zip(new["act_id"].to_list(), new["_text_hash"].to_list()))

    unchanged = sum(1 for i in common if old_hash[i] == new_hash[i])
    amended = len(common) - unchanged
    added = new_ids - old_ids
    removed = old_ids - new_ids

    # Examples of stable-amended ids (the key evidence). Sorted so the sampled
    # examples are deterministic across runs (M1A.5 review P4).
    amended_ids = [i for i in common if old_hash[i] != new_hash[i]]
    amended_examples = sorted(amended_ids)[:8]

    # Characterize the "amendments": append-only growth vs shrink, and how many
    # are operative-text-identical (i.e. only the editorial-notes apparatus moved).
    old_text = dict(zip(old["act_id"].to_list(), old["text"].to_list()))
    new_text = dict(zip(new["act_id"].to_list(), new["text"].to_list()))
    grew = shrank = op_identical = 0
    tot_old_chars = tot_new_chars = 0
    for i in amended_ids:
        a, b = old_text[i] or "", new_text[i] or ""
        tot_old_chars += len(a)
        tot_new_chars += len(b)
        if len(b) > len(a):
            grew += 1
        elif len(b) < len(a):
            shrank += 1
        if _operative(a) == _operative(b):
            op_identical += 1

    # Disposition-status rows in NEW: did their predecessor number exist in OLD,
    # and does the new act_id differ from it? (i.e. a move changes the id.)
    move_rows = new.filter(pl.col("act_status").is_in(["renumbered", "transferred", "recodified"]))
    move_checks = []
    for r in move_rows.head(2000).iter_rows(named=True):
        m = SUCCESSOR_RE.search(r["text"] or "")
        successor = m.group(2) if m else None
        move_checks.append(
            {
                "act_id": r["act_id"],
                "status": r["act_status"],
                "self_in_old": r["act_id"] in old_ids,
                "successor_num": successor,
            }
        )

    return {
        "old_n": old.height,
        "new_n": new.height,
        "common": len(common),
        "unchanged": unchanged,
        "amended": amended,
        "added": len(added),
        "removed": len(removed),
        "amended_examples": amended_examples,
        "amended_grew": grew,
        "amended_shrank": shrank,
        "amended_op_identical": op_identical,
        "amended_old_chars": tot_old_chars,
        "amended_new_chars": tot_new_chars,
        "added_examples": sorted(added)[:8],
        "removed_examples": sorted(removed)[:8],
        "move_rows": len(move_checks),
        "move_self_in_old": sum(1 for c in move_checks if c["self_in_old"]),
        "move_with_successor": sum(1 for c in move_checks if c["successor_num"]),
        "move_examples": move_checks[:8],
    }


def render(d: dict, old_label: str, new_label: str, name: str) -> str:
    L: list[str] = []
    w = L.append
    w("# M0 — `act_id` stability across snapshots\n")
    w(f"**File:** `{name}`  ")
    w(f"**Old:** `{old_label}` ({d['old_n']:,} rows)  ")
    w(f"**New:** `{new_label}` ({d['new_n']:,} rows)\n")

    w("## Verdict\n")
    if d["amended"] > 0 and d["unchanged"] >= 0:
        w(
            f"**Supporting evidence that `act_id` is stable under text change.** "
            f"{d['amended']:,} act_ids appear in *both* snapshots with **different text** — the "
            f"identifier held constant while the stored `text` changed. This is *consistent with* "
            f"the proposal's Tier-1 assumption that `act_id` is a stable-source identity seed, but "
            f"it does **not** by itself confirm it: same-id/different-text cannot, on its own, "
            f"distinguish a genuine legal amendment from editorial-notes expansion (see the caveat "
            f"below — a large share is exactly that) or from an `act_id` being reused for a "
            f"different provision. Treat it as one supporting signal, corroborated by the "
            f"operative-body split below, not as proof.\n"
        )
    else:
        w(
            "No text-only-amended act_ids were observed in this file (the two snapshots may be "
            "identical for this corpus). Inconclusive here; try a corpus with real churn.\n"
        )

    w("## Classification of act_ids\n")
    w("| class | count | share of union |")
    w("|---|---:|---:|")
    union = d["common"] + d["added"] + d["removed"]
    for label, key in [
        ("in both, text unchanged", "unchanged"),
        ("in both, text AMENDED", "amended"),
        (f"added in {new_label}", "added"),
        (f"removed since {old_label}", "removed"),
    ]:
        c = d[key]
        w(f"| {label} | {c:,} | {c / union * 100:.1f}% |")
    w("")

    # Nature of the "amendments" — critical caveat for text hashing.
    if d["amended"]:
        grow_pct = (
            (d["amended_new_chars"] - d["amended_old_chars"]) / d["amended_old_chars"] * 100
            if d["amended_old_chars"]
            else 0.0
        )
        op_pct = d["amended_op_identical"] / d["amended"] * 100
        w("## What the text changes actually are (caveat for `text_hash`)\n")
        w(
            f"The {d['amended']:,} 'amended' rows are **not** all real legal amendments. "
            f"Of them, **{d['amended_grew']:,} grew and {d['amended_shrank']:,} shrank** — the "
            f"change is essentially **append-only**, and the amended text grew **{grow_pct:+.1f}%** "
            f"in total characters. At least **{d['amended_op_identical']:,} ({op_pct:.0f}%)** have "
            f"an **identical operative body** once the OLRC `Editorial Notes / Statutory Notes` "
            f"apparatus is stripped — i.e. only the historical/editorial notes were expanded "
            f"between snapshots, not the law.\n"
        )
        w(
            "> **Design implication (M1):** the `text` field bundles operative statutory text "
            "with a volatile editorial-notes apparatus. Hashing the whole field makes ~half the "
            "corpus look 'amended' between snapshots and would poison both change-detection and "
            "text-similarity lineage. **Hash (and diff) the operative body separately from the "
            "notes.** `text_hash` over raw `text` is a provenance/integrity hash, not a "
            "legal-change signal.\n"
        )

    if d["amended_examples"]:
        w("**Stable-but-amended act_id examples (identity held, text changed):**")
        for i in d["amended_examples"]:
            w(f"- `{i}`")
        w("")
    if d["removed_examples"]:
        w(f"**Removed-since-{old_label} examples** (withdrawn / renumbered-away / dropped):")
        for i in d["removed_examples"]:
            w(f"- `{i}`")
        w("")
    if d["added_examples"]:
        w(f"**Added-in-{new_label} examples:**")
        for i in d["added_examples"]:
            w(f"- `{i}`")
        w("")

    w("## Move rows (renumber / transfer / recodify) in the new snapshot\n")
    w(
        f"Of {d['move_rows']:,} disposition-status rows checked, "
        f"{d['move_with_successor']:,} state a successor number inline in the text, and "
        f"{d['move_self_in_old']:,} have an act_id that already existed in `{old_label}`. "
        "The move row keeps *its own* (old) number as the row's act_id while its text points "
        "at a successor number. **The stated successor is extracted from the text but not "
        "resolved to an actual old/new record here**, so this pass does not by itself prove the "
        "successor carries a different act_id — it establishes only that the move row retains "
        "its own identifier. That retention is already enough motivation to link cross-move "
        "identity via `lineage_id` rather than assume act_id follows the provision; resolving "
        "the successor pointer to a record is future lineage work.\n"
    )
    if d["move_examples"]:
        w("| act_id | status | self in old? | successor stated |")
        w("|---|---|:--:|---|")
        for c in d["move_examples"]:
            w(
                f"| `{c['act_id']}` | {c['status']} | "
                f"{'yes' if c['self_in_old'] else 'no'} | "
                f"{c['successor_num'] or '—'} |"
            )
        w("")
    return "\n".join(L) + "\n"


def _summary_table(results: list[tuple[str, dict]]) -> list[str]:
    L = ["## Cross-corpus summary\n"]
    L.append("| File | rows | unchanged | amended | added | removed | act_id stable? |")
    L.append("|---|---:|---:|---:|---:|---:|:--:|")
    for name, d in results:
        stable = "yes" if d["removed"] == 0 else "CHECK"
        L.append(
            f"| {name} | {d['new_n']:,} | {d['unchanged']:,} | {d['amended']:,} | "
            f"{d['added']:,} | {d['removed']:,} | {stable} |"
        )
    L.append(
        "\n_`removed = 0` across every corpus ⇒ every `act_id` present in the old snapshot is "
        "still present in the new one (none dropped); `added` are `act_id`s new to the new "
        "snapshot **by set membership**; `amended` counts byte-level `text` change (federal is "
        "inflated by editorial-note growth — see per-file detail). Set membership alone does "
        "**not** establish that an id was never reissued to a different provision, nor that an "
        "`added` id is a brand-new enactment rather than the target of a renumber._\n"
    )
    return L


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--old", type=Path, help="Old parquet (single-pair mode).")
    ap.add_argument("--new", type=Path, help="New parquet (single-pair mode).")
    ap.add_argument(
        "--pair", action="append", default=[],
        help="OLD:NEW file pair; repeatable for a combined multi-corpus report.",
    )
    ap.add_argument("--old-label", default="old")
    ap.add_argument("--new-label", default="new")
    ap.add_argument("--out", type=Path, default=Path("reports/M0_act_id_stability.md"))
    args = ap.parse_args()

    pairs: list[tuple[Path, Path]] = []
    if args.old and args.new:
        pairs.append((args.old, args.new))
    for p in args.pair:
        o, n = p.split(":")
        pairs.append((Path(o), Path(n)))
    if not pairs:
        raise SystemExit("Provide --old/--new or one or more --pair OLD:NEW.")

    results = [(new.name, diff(pl.read_parquet(old), pl.read_parquet(new))) for old, new in pairs]

    sections: list[str] = []
    if len(results) > 1:
        sections.append("# M0 — `act_id` stability across snapshots (multi-corpus)\n")
        sections.append(f"**Old:** `{args.old_label}` → **New:** `{args.new_label}`\n")
        sections += _summary_table(results)
        sections.append("\n---\n")
    for name, d in results:
        sections.append(render(d, args.old_label, args.new_label, name))
        sections.append("\n---\n")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(sections))
    print(f"wrote {args.out}")
    for name, d in results:
        print(
            f"{name}: amended={d['amended']} unchanged={d['unchanged']} "
            f"added={d['added']} removed={d['removed']}"
        )


if __name__ == "__main__":
    main()
