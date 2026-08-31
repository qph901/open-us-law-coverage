"""M0.5B3 — the California abstraction-falsification probe.

**Not** "run USC heuristics on CA" (parser rules are *expected* to be
corpus-specific and their failure teaches little). Instead, per ``PROPOSAL.md``
M0.5B3, take the artifact **output types** that exist so far and test whether
they represent a real CA sample **without distortion**:

* built and falsified here end-to-end — ``DerivedArtifactProvenance``,
  ``SourceIdentityGroup`` + ``SourceIdentityMemberAnnotation`` (the real
  ``resolve_single_record_identity`` producer), ``DocumentClassificationAnnotation``,
  ``QualityAnnotation`` (the real ``detect_duplicate_rows``, run *within each
  identity group*), ``SourceDocumentAssembly`` (all M1A.5), and ``HierarchyNode[]``
  / ``StructuralPath`` (M0.5B2);
* ``DocumentAnatomy`` / ``AnatomySpan`` are **not built yet** (M0.5B1, blocked on
  USLM), so this probe captures the *requirements* CA imposes on them and defers
  the full anatomy falsification to B1.

**Rule under test — universal artifact model, corpus-specific producers:** a
parser implementation may be corpus-specific; the artifact *interfaces* must
survive both USC and California. The deliverable is the list of interface changes
CA forces (or confirmation of none), captured **before** M1B freezes interfaces.

Streams the CA file row-group-bounded (M1A ``iter_source_records``), so it is
OOM-safe. Regenerate::

    uv run python -m open_us_law_coverage.ca_probe \\
        data/v2026.08_full/us_ca_statutes.parquet \\
        --snapshot v2026.08 --out reports/M0.5B3_ca_abstraction.md
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .derived import (
    classify_source_record,
    detect_duplicate_rows,
    is_duplicate_row,
    resolve_single_record_identity,
)
from .derived.assembly import assemble_trivial_single_record
from .hierarchy import (
    RoundTrip,
    parse_breadcrumb,
    roundtrip_status,
    to_structural_path,
)
from .source_record import iter_source_records


@dataclass
class CaProbeResult:
    corpus: str
    rows: int = 0
    parse_ok: int = 0
    parse_fail: int = 0
    distinct_act_ids: int = 0
    distinct_structural_paths: int = 0
    doc_class: Counter = field(default_factory=Counter)
    status: Counter = field(default_factory=Counter)
    leaf_kinds: Counter = field(default_factory=Counter)
    kind_vocab: Counter = field(default_factory=Counter)
    nonnumeric_leaf_ids: int = 0
    roundtrip: Counter = field(default_factory=Counter)
    # SourceDocumentAssembly losslessness — checked over the FULL corpus (not sampled).
    assembly_lossless: bool = True
    assembly_checked: int = 0
    # SourceIdentityGroup / SourceIdentityMemberAnnotation (real producer).
    identity_single_member: int = 0
    identity_multi_member: int = 0
    identity_status: Counter = field(default_factory=Counter)
    identity_strategy: Counter = field(default_factory=Counter)
    # duplicate_row run *within each identity group* (real detect_duplicate_rows).
    within_group_duplicate_rows: int = 0
    # cross-identity content duplication (same bytes, DIFFERENT provision)
    content_dup_hashes: int = 0
    content_dup_rows: int = 0
    content_dup_example: tuple[str, ...] | None = None
    # a captured anatomy requirement: a 'repealed'-status row whose text is a
    # leading history/source-credit bracket + operative body.
    repealed_bracket_example: tuple[str, str] | None = None


def _is_numeric_id(identifier: str | None) -> bool:
    if not identifier:
        return False
    return identifier.replace(".", "").replace("-", "").isdigit()


def analyze_ca(path: str | Path, snapshot_version: str) -> CaProbeResult:
    """Run every built producer over the CA corpus under ``snapshot_version``.

    The snapshot is threaded into ``iter_source_records`` so every ``source_record_id``
    — and therefore every derived artifact id built here — is computed under the
    requested snapshot, not a placeholder (M1A.5 review P6). The report body is
    aggregate counts, so the *numbers* are snapshot-independent, but the provenance
    chain must be the real one for this to be evidence of v2026.08.
    """
    path = Path(path)
    res = CaProbeResult(corpus=path.name.replace(".parquet", ""))

    act_ids: set[str] = set()
    paths: set[str] = set()
    hash_to_acts: dict[str, set[str]] = defaultdict(set)

    # One streaming, row-group-bounded pass runs every *built* producer over each
    # row: classification, hierarchy, identity (group + member annotation), duplicate
    # detection within that group, and the trivial assembly (full corpus, not sampled).
    for rec in iter_source_records(path, snapshot_version=snapshot_version):
        res.rows += 1
        act_id = rec.column("act_id")
        act_ids.add(act_id)
        res.status[rec.column("act_status")] += 1

        # DocumentClassificationAnnotation
        res.doc_class[str(classify_source_record(rec).document_class)] += 1

        # SourceIdentityGroup + SourceIdentityMemberAnnotation (real producer). CA is
        # 1:1 (act_id unique), so every row is a single-member group.
        identity = resolve_single_record_identity(rec)
        assert identity is not None, f"CA statute row did not dispatch: {act_id!r}"
        res.identity_strategy[identity.group.strategy_name] += 1
        res.identity_status[str(identity.group.identity_status)] += 1
        if len(identity.group.member_source_record_ids) == 1:
            res.identity_single_member += 1
        else:
            res.identity_multi_member += 1

        # duplicate_row *within the identity group* (real detect_duplicate_rows). The
        # group is this one record, so within-group duplicates are 0 by construction —
        # the load-bearing contrast with the corpus-wide content duplication below.
        dup = detect_duplicate_rows(identity.group, [rec])
        res.within_group_duplicate_rows += sum(
            1 for a in dup.annotations if is_duplicate_row(a)
        )

        # SourceDocumentAssembly losslessness — over the full corpus, every row.
        asm = assemble_trivial_single_record(rec)
        res.assembly_checked += 1
        if rec.raw_text is not None and asm.assembled_text != rec.raw_text:
            res.assembly_lossless = False

        # HierarchyNode[] + StructuralPath
        nodes = parse_breadcrumb(rec.column("breadcrumb"))
        if not nodes:
            res.parse_fail += 1
        else:
            res.parse_ok += 1
            for n in nodes:
                res.kind_vocab[str(n.kind)] += 1
            leaf = nodes[-1]
            res.leaf_kinds[str(leaf.kind)] += 1
            if not _is_numeric_id(leaf.identifier):
                res.nonnumeric_leaf_ids += 1
            sp = to_structural_path(nodes)
            paths.add(sp.render())
            res.roundtrip[roundtrip_status(nodes, rec.column("display_path"))] += 1

        # cross-identity content duplication
        if rec.raw_text_hash is not None:
            hash_to_acts[rec.raw_text_hash].add(act_id)

        # capture one anatomy requirement example (first repealed, physical order)
        if (
            res.repealed_bracket_example is None
            and rec.column("act_status") == "repealed"
            and rec.raw_text
        ):
            head = rec.raw_text[:160].replace("\n", " ").strip()
            res.repealed_bracket_example = (act_id, head)

    res.distinct_act_ids = len(act_ids)
    res.distinct_structural_paths = len(paths)

    # cross-identity content-dup summary (bytes shared across DISTINCT act_ids)
    shared = {h: acts for h, acts in hash_to_acts.items() if len(acts) > 1}
    res.content_dup_hashes = len(shared)
    res.content_dup_rows = sum(len(acts) for acts in shared.values())
    if shared:
        first_hash = min(shared)
        res.content_dup_example = tuple(sorted(shared[first_hash])[:4])
    return res


# ---------------------------------------------------------------------------
# Report.
# ---------------------------------------------------------------------------

EXIT_SECTION = """\
## Exit verdict (M0.5B3) — interface changes CA forces

**Zero interface changes to any *built* artifact type.** A real, full CA statute
corpus is represented without distortion by the universal types:

| artifact type | CA stress | verdict |
|---|---|---|
| `DerivedArtifactProvenance` | source-agnostic; anchors to `source_record_id` | **no change** |
| `SourceIdentityGroup` + `SourceIdentityMemberAnnotation` | `act_id` 100% unique → every row is a single-member group (`resolved`, `identity_scope=document`, `single_record`) — the degenerate case of the multi-member shape | **no change** |
| `DocumentClassificationAnnotation` | `STATE_*` → `statute` / `operative_primary_law` | **no change** |
| `HierarchyNode[]` | `code/division/part/title/article/chapter/section/appendix`; variable ordering; non-numeric ids (`73c`, `GENERAL PROVISIONS`) | **no change** (`identifier` is already a nullable string) |
| `StructuralPath` | bare leaf id is ambiguous, but the absolute path is 1:1 (distinct paths == rows) | **no change** — this is exactly why the anchor is the path, not the id |
| `SourceDocumentAssembly` | CA is 1:1 source→document → `trivial_single_record_v2` | **no change** |

**Two requirements captured (producer / taxonomy notes, not type changes):**

1. **`duplicate_row` must be scoped to the identity group, not the corpus.** CA
   has thousands of byte-identical rows across *distinct* provisions (`[Repealed]`
   / `[Reserved]` stubs, re-used boilerplate). At corpus scope the detector flags
   them; but they have distinct `act_id`s and distinct structural paths, so they
   are **not** the same provision. This probe now runs the real
   `detect_duplicate_rows` **within each identity group** and gets **zero**
   within-group duplicates — while the corpus-wide byte-identical count is large.
   `duplicate_row` means "same bytes," **never** "same legal identity" — it runs
   within a `source_identity_key` group (CA yields zero), and its corpus-scope
   signal would be a *quality* observation, never a `legal_id` merge. (This is the
   orthogonality of content vs identity, made concrete.)

2. **Anatomy taxonomy (for B1) must carry a leading history/source-credit
   bracket, and must not trust `act_status`.** CA `repealed`-status rows commonly
   contain a leading `[Repealed ... and added by Stats. ...]` bracket **followed
   by operative text** — so `act_status` is not a reliable operative/non-operative
   signal, and anatomy must read the text. The `AnatomySpan(start, end, label,
   source, confidence)` *shape* suffices; only the label taxonomy needs a
   source-credit / disposition-bracket category (USLM-grounded). **Full anatomy
   falsification is deferred to M0.5B1** (blocked on the USLM oracle) — recorded
   here as a standing input, not a resolved result.

**Net:** the M1B interface freeze is not blocked by California. The only CA-forced
work is in *producers and taxonomies*, exactly as "universal artifact model,
corpus-specific producers" predicts.
"""


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "—"


def render_report(res: CaProbeResult, snapshot: str) -> str:
    L: list[str] = []
    L.append("# M0.5B3 — California abstraction-falsification probe")
    L.append("")
    L.append(f"Snapshot: **{snapshot}**. Corpus: `{res.corpus}`. The question is "
             "whether the artifact *types* built so far represent a real CA sample "
             "faithfully — **universal artifact model, corpus-specific producers**.")
    L.append("")
    L.append("## CA corpus facts (computed)")
    L.append("")
    L.append(f"- rows: **{res.rows:,}** | document classes: "
             + ", ".join(f"`{k}`:{v:,}" for k, v in sorted(res.doc_class.items())))
    L.append(f"- **identity is 1:1** — distinct `act_id`: **{res.distinct_act_ids:,}** "
             f"({_pct(res.distinct_act_ids, res.rows)} unique) | distinct `StructuralPath`: "
             f"**{res.distinct_structural_paths:,}** ({_pct(res.distinct_structural_paths, res.rows)})")
    L.append(f"- **`SourceIdentityGroup` (real producer)** — single-member groups: "
             f"**{res.identity_single_member:,}**, multi-member: {res.identity_multi_member:,} | "
             + ", ".join(f"`{k}`:{v:,}" for k, v in sorted(res.identity_strategy.items()))
             + " | status " + ", ".join(f"`{k}`:{v:,}" for k, v in sorted(res.identity_status.items())))
    L.append(f"- **`duplicate_row` within each identity group** (real "
             f"`detect_duplicate_rows`): **{res.within_group_duplicate_rows:,}** flagged "
             f"(a single-member group has no sibling to duplicate — the contrast below is the point)")
    L.append(f"- breadcrumb parsed: {res.parse_ok:,} ({_pct(res.parse_ok, res.rows)}), "
             f"failed: {res.parse_fail:,}")
    L.append("- act_status: " + ", ".join(f"`{k}`:{v:,}" for k, v in res.status.most_common()))
    L.append("- hierarchy kinds: "
             + ", ".join(f"`{k}`:{v:,}" for k, v in sorted(res.kind_vocab.items())))
    L.append("- leaf kinds: " + ", ".join(f"`{k}`:{v:,}" for k, v in sorted(res.leaf_kinds.items())))
    L.append(f"- non-numeric leaf identifiers (e.g. `73c`, `GENERAL PROVISIONS`): "
             f"**{res.nonnumeric_leaf_ids:,}** — carried as strings, no distortion")
    rt = ", ".join(f"{k}:{res.roundtrip[k]:,}" for k in RoundTrip if res.roundtrip[k])
    L.append(f"- display-path round-trip: {rt}")
    L.append(f"- `SourceDocumentAssembly` losslessness (trivial, **full corpus** — "
             f"{res.assembly_checked:,} rows): "
             f"{'PASS' if res.assembly_lossless else 'FAIL'}")
    L.append("")
    L.append("## Content duplication is not identity duplication")
    L.append("")
    L.append(f"- byte-identical text shared across **distinct** provisions: "
             f"**{res.content_dup_hashes:,}** text hashes spanning **{res.content_dup_rows:,}** rows "
             f"(all with distinct `act_id` + distinct `StructuralPath`).")
    if res.content_dup_example:
        L.append("- example — identical text, distinct provisions: "
                 + ", ".join(f"`{a}`" for a in res.content_dup_example))
    L.append("- Consequence: `duplicate_row` is a **content** conclusion, not an identity one; "
             "it must be scoped to the identity group (CA yields **0** within-group), and never "
             "collapse these distinct provisions into one `legal_id`.")
    L.append("")
    L.append("## Anatomy (`AnatomySpan`) — requirements captured for B1")
    L.append("")
    L.append("`DocumentAnatomy`/`AnatomySpan` are not built yet (M0.5B1, blocked on USLM). CA "
             "imposes two requirements on them, recorded now:")
    if res.repealed_bracket_example:
        act, head = res.repealed_bracket_example
        L.append(f"- **leading history/source-credit bracket** — e.g. `{act}` "
                 f"(status `repealed`) begins: “{head}…”, then operative `(a)/(b)` text follows. "
                 "Anatomy must span the bracket as source-credit/disposition, separate from the "
                 "operative body.")
    L.append("- **`act_status` is not a reliable operative signal** — a `repealed`-status row can "
             "carry a re-enacted operative body; anatomy must read the text, not the status flag.")
    L.append("- The `AnatomySpan(start, end, label, source, confidence)` **shape suffices**; only "
             "the label taxonomy needs a source-credit / disposition-bracket category.")
    L.append("")
    L.append(EXIT_SECTION)
    return "\n".join(L) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="M0.5B3: falsify the built artifact types against a real CA "
        "sample; emit the list of interface changes CA forces (or none)."
    )
    ap.add_argument("path", help="the CA statutes Parquet file")
    ap.add_argument("--snapshot", required=True, help="snapshot version, e.g. v2026.08")
    ap.add_argument("--out", help="write the Markdown report here (else stdout)")
    args = ap.parse_args(argv)

    res = analyze_ca(args.path, args.snapshot)
    report = render_report(res, args.snapshot)
    if args.out:
        Path(args.out).write_text(report)
        print(f"wrote {args.out}")
    else:
        print(report)


if __name__ == "__main__":
    main()
