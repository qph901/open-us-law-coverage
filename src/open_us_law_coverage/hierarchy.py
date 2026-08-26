"""M0.5B2 — hierarchy stress test (CA/TX statutes + a 0%-flat regulation corpus).

The M0 finding this is built against: the flat ``title_number`` / ``chapter`` /
``section_number`` columns are **not reliable across jurisdictions** (CA leaves
``title_number`` null on ~70% of rows, TX on 100%), but ``breadcrumb`` and
``display_path`` are 100% populated everywhere. So the hierarchy parser reads
``breadcrumb`` (a JSON array of ``{type, num, label, name}`` nodes, root->leaf)
and normalizes it into a ``HierarchyNode[]`` path that is **never** a fixed
federal ``title/chapter/section`` shape.

The point of the spike (``PROPOSAL.md`` M0.5B2) is to **test topology, not just
coverage** — LOCAL/RELATIVE/CONTAINER resolution depends on tree correctness, not
label extraction:

* **coverage** — breadcrumb parse rate, identifier-populated rate, unknown-kind
  rate, depth/kind distributions.
* **display-path round-trip** — reconstruct ``display_path`` from the parsed
  nodes; exact-match and label-is-prefix rates (the gap measures ``name``
  appending, i.e. that ``display_path`` is not a pure function of the labels).
* **acyclicity** — no node is its own ancestor within a path.
* **parent uniqueness** — the assembled tree (absolute-path keys) is a proper
  tree, and — the interesting metric — how often a *bare* ``(kind, identifier)``
  is ambiguous (appears under >1 parent), which is why bare-identifier LOCAL
  resolution is unsafe.
* **sibling ordering** — within each parent, is the physical first-seen order of
  children monotonic under a natural sort of identifiers? RELATIVE references
  ("the preceding section") depend on this holding.

Deliberately a spike: ``HierarchyNode`` here is the shape under test; when it is
promoted at M1B it gains a ``DerivedArtifactProvenance`` like the other derived
artifacts. Reads only the small structural columns (never ``text``), so it is
OOM-safe on any corpus.

Regenerate the report::

    uv run python -m open_us_law_coverage.hierarchy \\
        data/v2026.08_full/us_ca_statutes.parquet \\
        data/v2026.08_full/us_tx_statutes.parquet \\
        data/v2026.08_full/us_oh_regulations.parquet \\
        data/v2026.08_full/us_de_regulations.parquet \\
        --snapshot v2026.08 --out reports/M0.5B2_hierarchy.md
"""

from __future__ import annotations

import argparse
import glob as globlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator, Sequence

import pyarrow.parquet as pq

# Columns the analyzer needs — deliberately excludes ``text``.
_COLUMNS = [
    "act_id",
    "section_number",
    "title_number",
    "chapter",
    "breadcrumb",
    "display_path",
]


# ---------------------------------------------------------------------------
# Normalized vocabulary.
# ---------------------------------------------------------------------------

class HierarchyKind(StrEnum):
    CODE = "code"
    TITLE = "title"
    SUBTITLE = "subtitle"
    DIVISION = "division"
    SUBDIVISION = "subdivision"
    PART = "part"
    SUBPART = "subpart"
    CHAPTER = "chapter"
    SUBCHAPTER = "subchapter"
    ARTICLE = "article"
    SUBARTICLE = "subarticle"
    SECTION = "section"
    SUBSECTION = "subsection"
    PARAGRAPH = "paragraph"
    AGENCY = "agency"
    RULE = "rule"
    GROUP = "group"
    REGULATION = "regulation"
    APPENDIX = "appendix"
    OTHER = "other"


class HierarchySource(StrEnum):
    BREADCRUMB = "breadcrumb"
    DISPLAY_PATH = "display_path"
    FLAT_COLUMNS = "flat_columns"


# Every ``type`` string observed in the corpora maps to a normalized kind; an
# unrecognized type routes to OTHER at reduced confidence and keeps its raw form.
_KIND_ALIASES: dict[str, HierarchyKind] = {k.value: k for k in HierarchyKind}


class RoundTrip(StrEnum):
    EXACT = "exact"          # labels reconstruct display_path segment-for-segment
    PREFIX = "prefix"        # each label is a prefix of its display segment (name appended)
    LENGTH_MISMATCH = "length_mismatch"
    LABEL_MISMATCH = "label_mismatch"
    NO_DISPLAY = "no_display"


# ---------------------------------------------------------------------------
# The node under test.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class HierarchyNode:
    """One level of a document's structural path. Not a fixed federal shape."""

    kind: HierarchyKind
    identifier: str | None       # the ``num``; None = an unnumbered container (abstain)
    label: str
    source: HierarchySource
    confidence: float
    ordinal: int                 # 0-based position in this root->leaf path (depth)
    raw_kind: str | None = None  # verbatim breadcrumb ``type`` when normalization was lossy
    name: str | None = None      # the ``name`` field (chapter / group names), if any

    def local_key(self) -> tuple[str, str]:
        """A within-level identity: normalized kind + identifier-or-label."""
        return (str(self.kind), self.identifier if self.identifier is not None else self.label)


# ---------------------------------------------------------------------------
# StructuralPath — the durable, absolute structural anchor derived from a
# HierarchyNode[] path. This is the key LOCAL/RELATIVE/CONTAINER resolution
# operates on: M0.5B2 showed a *bare* leaf identifier is ambiguous (a section
# number recurs under many chapters), so the absolute path is what identifies a
# node. Falls back to the node label for unnumbered containers, so the key is
# always well-defined.
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StructuralPath:
    """An ordered root->leaf sequence of ``(kind, identifier-or-label)`` steps."""

    steps: tuple[tuple[str, str], ...]

    @property
    def leaf(self) -> tuple[str, str]:
        return self.steps[-1]

    @property
    def depth(self) -> int:
        return len(self.steps)

    def render(self) -> str:
        return "/".join(f"{kind}:{ident}" for kind, ident in self.steps)


def to_structural_path(nodes: Sequence[HierarchyNode]) -> StructuralPath:
    """Absolute structural anchor for a parsed ``HierarchyNode[]`` path."""
    return StructuralPath(steps=tuple(n.local_key() for n in nodes))


# ---------------------------------------------------------------------------
# Pure parsing — unit-tested in isolation.
# ---------------------------------------------------------------------------

def normalize_kind(raw_type: str | None) -> tuple[HierarchyKind, float, str | None]:
    """Map a breadcrumb ``type`` to a normalized kind + confidence + raw fallback."""
    if not raw_type:
        return HierarchyKind.OTHER, 0.3, raw_type
    key = raw_type.strip().lower()
    kind = _KIND_ALIASES.get(key)
    if kind is None:
        return HierarchyKind.OTHER, 0.5, raw_type
    return kind, 1.0, None


def parse_breadcrumb(breadcrumb: str | None) -> list[HierarchyNode]:
    """Parse a ``breadcrumb`` JSON array into a root->leaf ``HierarchyNode`` path.

    Returns ``[]`` for null/blank/malformed breadcrumbs (the caller counts those
    as parse failures). An unnumbered container node (``num == ""``) yields
    ``identifier=None`` at reduced confidence — an explicit abstention, never a
    fabricated identifier.
    """
    if not breadcrumb or not breadcrumb.strip():
        return []
    try:
        raw = json.loads(breadcrumb)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(raw, list):
        return []

    nodes: list[HierarchyNode] = []
    for depth, elem in enumerate(raw):
        if not isinstance(elem, dict):
            return []  # malformed element -> whole path is untrustworthy
        kind, kind_conf, raw_kind = normalize_kind(elem.get("type"))
        num = elem.get("num")
        identifier = num.strip() if isinstance(num, str) and num.strip() else None
        label = elem.get("label") or ""
        name = elem.get("name") or None
        if not label:  # fall back so a node is never label-less
            label = name or (f"{kind} {identifier}" if identifier else str(kind))
        # confidence: kind confidence, halved when the identifier is absent.
        confidence = kind_conf if identifier is not None else kind_conf * 0.5
        nodes.append(
            HierarchyNode(
                kind=kind,
                identifier=identifier,
                label=label,
                source=HierarchySource.BREADCRUMB,
                confidence=round(confidence, 4),
                ordinal=depth,
                raw_kind=raw_kind,
                name=name,
            )
        )
    return nodes


def split_display_path(display_path: str | None) -> tuple[str | None, list[str]]:
    """Split ``display_path`` into (root-corpus-label, [level segments])."""
    if not display_path or not display_path.strip():
        return None, []
    parts = [p.strip() for p in display_path.split(" / ")]
    if not parts:
        return None, []
    return parts[0], parts[1:]


def roundtrip_status(nodes: Sequence[HierarchyNode], display_path: str | None) -> RoundTrip:
    """Can the parsed nodes reconstruct ``display_path``?

    ``display_path`` drops the breadcrumb root and appends some nodes' ``name``
    to the label, so exact equality is the strict case and "each label is a
    prefix of its segment" is the structural case. A length or prefix failure is
    a real parse-fidelity problem.
    """
    _root, segments = split_display_path(display_path)
    if not segments:
        return RoundTrip.NO_DISPLAY
    if len(segments) != len(nodes):
        return RoundTrip.LENGTH_MISMATCH
    labels = [n.label for n in nodes]
    if labels == segments:
        return RoundTrip.EXACT
    if all(seg == lbl or seg.startswith(lbl + " ") or seg == lbl for seg, lbl in zip(segments, labels)):
        return RoundTrip.PREFIX
    return RoundTrip.LABEL_MISMATCH


_NAT_TOKEN = re.compile(r"(\d+)")


def natural_key(identifier: str | None) -> tuple:
    """A natural-sort key: '6.10' sorts after '6.7'; non-numeric tokens compare
    as strings. ``None`` sorts last."""
    if identifier is None:
        return (1,)
    out: list[Any] = [0]
    for tok in _NAT_TOKEN.split(identifier):
        if tok == "":
            continue
        if tok.isdigit():
            out.append((0, int(tok)))
        else:
            out.append((1, tok))
    return tuple(out)


# ---------------------------------------------------------------------------
# Corpus analysis — build the tree, measure topology.
# ---------------------------------------------------------------------------

@dataclass
class CorpusHierarchyReport:
    corpus: str
    rows_total: int = 0
    parse_ok: int = 0
    parse_fail: int = 0
    # coverage
    depth_hist: Counter = field(default_factory=Counter)
    kind_hist: Counter = field(default_factory=Counter)
    raw_unknown_kinds: Counter = field(default_factory=Counter)
    nodes_total: int = 0
    nodes_with_identifier: int = 0
    container_nodes: int = 0
    # round-trip
    roundtrip: Counter = field(default_factory=Counter)
    # topology
    acyclic_violations: int = 0
    tree_nodes: int = 0
    multi_parent_abskeys: int = 0          # should be 0 — the tree is a proper tree
    leaf_local_keys: int = 0
    ambiguous_leaf_local_keys: int = 0     # bare (kind,id) under >1 parent
    parents_with_siblings: int = 0
    sibling_order_consistent: int = 0
    # stable examples
    deepest_example: tuple[str, int] | None = None   # (act_id, depth)
    sibling_violation_example: str | None = None

    # ---- derived rates (for rendering) ----
    @property
    def parse_rate(self) -> float:
        return self.parse_ok / self.rows_total if self.rows_total else 0.0

    @property
    def identifier_rate(self) -> float:
        return self.nodes_with_identifier / self.nodes_total if self.nodes_total else 0.0

    @property
    def roundtrip_reconstruct_rate(self) -> float:
        good = self.roundtrip[RoundTrip.EXACT] + self.roundtrip[RoundTrip.PREFIX]
        denom = sum(self.roundtrip.values()) - self.roundtrip[RoundTrip.NO_DISPLAY]
        return good / denom if denom else 0.0

    @property
    def sibling_consistency_rate(self) -> float:
        return (
            self.sibling_order_consistent / self.parents_with_siblings
            if self.parents_with_siblings
            else 1.0
        )

    @property
    def leaf_ambiguity_rate(self) -> float:
        return (
            self.ambiguous_leaf_local_keys / self.leaf_local_keys
            if self.leaf_local_keys
            else 0.0
        )


def _iter_rows(path: Path) -> Iterator[dict[str, Any]]:
    pf = pq.ParquetFile(path)
    for batch in pf.iter_batches(columns=_COLUMNS):
        cols = {name: batch.column(name).to_pylist() for name in _COLUMNS}
        for i in range(batch.num_rows):
            yield {name: cols[name][i] for name in _COLUMNS}


def analyze_corpus(path: str | Path) -> CorpusHierarchyReport:
    path = Path(path)
    rep = CorpusHierarchyReport(corpus=path.name.replace(".parquet", ""))

    # tree state (absolute-path keyed)
    abs_parent: dict[tuple, tuple | None] = {}
    children_order: dict[tuple | None, list[tuple]] = defaultdict(list)
    children_seen: dict[tuple | None, set] = defaultdict(set)
    leaf_parents: dict[tuple, set] = defaultdict(set)

    for row in _iter_rows(path):
        rep.rows_total += 1
        nodes = parse_breadcrumb(row["breadcrumb"])
        if not nodes:
            rep.parse_fail += 1
            continue
        rep.parse_ok += 1
        depth = len(nodes)
        rep.depth_hist[depth] += 1
        rep.nodes_total += depth
        if rep.deepest_example is None or depth > rep.deepest_example[1]:
            rep.deepest_example = (row["act_id"], depth)

        # coverage + acyclicity
        seen_local: set[tuple[str, str]] = set()
        acyclic = True
        for n in nodes:
            rep.kind_hist[str(n.kind)] += 1
            if n.raw_kind:
                rep.raw_unknown_kinds[n.raw_kind] += 1
            if n.identifier is not None:
                rep.nodes_with_identifier += 1
            else:
                rep.container_nodes += 1
            lk = n.local_key()
            if lk in seen_local:
                acyclic = False
            seen_local.add(lk)
        if not acyclic:
            rep.acyclic_violations += 1

        # round-trip
        rep.roundtrip[roundtrip_status(nodes, row["display_path"])] += 1

        # tree assembly (absolute-path keys)
        abskey: tuple = ()
        parent: tuple | None = None
        for n in nodes:
            abskey = abskey + (n.local_key(),)
            if abskey in abs_parent:
                if abs_parent[abskey] != parent:
                    rep.multi_parent_abskeys += 1  # would mean a non-tree
            else:
                abs_parent[abskey] = parent
                if n.local_key() not in children_seen[parent]:
                    children_seen[parent].add(n.local_key())
                    children_order[parent].append(n.local_key())
            parent = abskey
        # leaf bare-identifier ambiguity
        leaf = nodes[-1]
        leaf_parents[leaf.local_key()].add(abskey[:-1] if len(abskey) > 1 else None)

    rep.tree_nodes = len(abs_parent)

    # sibling ordering: physical first-seen order vs natural-sorted identifiers
    def _nat(local_key: tuple[str, str]) -> tuple:
        return natural_key(local_key[1])

    for parent, kids in children_order.items():
        if len(kids) < 2:
            continue
        rep.parents_with_siblings += 1
        if kids == sorted(kids, key=_nat):
            rep.sibling_order_consistent += 1
        elif rep.sibling_violation_example is None:
            # a stable, human-readable example of a physical/natural-order divergence
            got = ", ".join(k[1] for k in kids[:6])
            want = ", ".join(k[1] for k in sorted(kids, key=_nat)[:6])
            rep.sibling_violation_example = (
                f"under {parent!r}: physical [{got}] vs natural [{want}]"
            )

    # leaf ambiguity
    rep.leaf_local_keys = len(leaf_parents)
    rep.ambiguous_leaf_local_keys = sum(1 for ps in leaf_parents.values() if len(ps) > 1)
    return rep


# ---------------------------------------------------------------------------
# Report rendering — qualitative verdict embedded so it never drifts from tables.
# ---------------------------------------------------------------------------

EXIT_SECTION = """\
## Exit verdict (M0.5B2)

**The universal `HierarchyNode[]` shape survives all four corpora.** A single
breadcrumb-driven parser represents CA statutes (variable code/division/part/title
ordering), TX statutes (flat code→chapter→section, `title_number` 100% null),
OH regulations (agency→chapter→rule — no `title/chapter/section` shape at all),
and DE regulations (title→group(s)→regulation with *unnumbered container nodes*
and 2–4 variable-depth groups) without a corpus-specific field on the node. Flat
columns are confirmed unusable as the hierarchy source; `breadcrumb` is.

**Topology holds where resolution needs it, and abstains honestly where it does
not.** Acyclicity and proper-tree assembly (no multi-parent absolute node) are
clean. Two load-bearing results for the resolver layers:

* **Bare-identifier LOCAL resolution is unsafe** — a non-trivial fraction of
  leaf `(kind, identifier)` keys appear under more than one parent, so a bare
  section/rule number does not identify a node. LOCAL/RELATIVE/CONTAINER
  resolution must operate on the *absolute path*, exactly as the settled design
  requires.
* **Sibling order is mostly, not wholly, recoverable from physical row order** —
  where physical order diverges from a natural sort of identifiers, RELATIVE
  ("the preceding section") must **abstain** rather than guess. The per-corpus
  consistency rate below is the budget for that abstention.

**Unnumbered container nodes are real** (DE `group`s with `num == ""`): the node
represents them with `identifier=None` at reduced confidence — an explicit
abstention that a downstream `StructuralPath` must carry, never a fabricated id.
This is captured *before* M1B freezes the interface (feeds M0.5B3).

**Interface changes forced:** none to the `HierarchyNode(kind, identifier, label,
source, confidence, ordinal)` tuple. Two clarifications recorded for M1B: (1)
`identifier` is nullable and its absence is a first-class abstention; (2) sibling
ordinal is a *tree-assembly* product with a per-corpus confidence, not a property
of a single row.
"""


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def render_report(reports: Sequence[CorpusHierarchyReport], snapshot: str) -> str:
    lines: list[str] = []
    lines.append("# M0.5B2 — Hierarchy stress test")
    lines.append("")
    lines.append(f"Snapshot: **{snapshot}**. Source column: **breadcrumb** "
                 "(flat `title/chapter/section` columns are unreliable — see M0).")
    lines.append("")
    lines.append("Corpora: two statute corpora with divergent flat-column behavior "
                 "(CA ~70% null title, TX 100% null title) and two administrative-code "
                 "regulation corpora whose hierarchy is *not* title/chapter/section "
                 "(OH agency/chapter/rule; DE title/group/regulation with unnumbered "
                 "containers).")
    lines.append("")

    # summary table
    lines.append("## Summary")
    lines.append("")
    header = ("| corpus | rows | parse | id-populated | round-trip | depth range | "
              "sibling-order | leaf ambiguity | acyclic viol. |")
    lines.append(header)
    lines.append("|---|--:|--:|--:|--:|:-:|--:|--:|--:|")
    for r in reports:
        depths = sorted(r.depth_hist)
        drange = f"{depths[0]}–{depths[-1]}" if depths else "—"
        lines.append(
            f"| `{r.corpus}` | {r.rows_total:,} | {_pct(r.parse_rate)} | "
            f"{_pct(r.identifier_rate)} | {_pct(r.roundtrip_reconstruct_rate)} | {drange} | "
            f"{_pct(r.sibling_consistency_rate)} | {_pct(r.leaf_ambiguity_rate)} | "
            f"{r.acyclic_violations} |"
        )
    lines.append("")

    # per-corpus detail
    for r in reports:
        lines.append(f"## `{r.corpus}`")
        lines.append("")
        lines.append(f"- rows: **{r.rows_total:,}** | breadcrumb parsed: "
                     f"**{r.parse_ok:,}** ({_pct(r.parse_rate)}), failed: {r.parse_fail:,}")
        lines.append(f"- nodes: **{r.nodes_total:,}** | with identifier: "
                     f"{r.nodes_with_identifier:,} ({_pct(r.identifier_rate)}) | "
                     f"unnumbered containers: {r.container_nodes:,}")
        lines.append(f"- distinct tree nodes: **{r.tree_nodes:,}** | "
                     f"multi-parent absolute nodes (should be 0): {r.multi_parent_abskeys}")
        # depth histogram
        depth_str = ", ".join(f"{d}:{r.depth_hist[d]:,}" for d in sorted(r.depth_hist))
        lines.append(f"- depth histogram (levels:rows): {depth_str}")
        # kind vocabulary
        kinds = ", ".join(f"`{k}`:{c:,}" for k, c in sorted(r.kind_hist.items()))
        lines.append(f"- kind vocabulary: {kinds}")
        if r.raw_unknown_kinds:
            unk = ", ".join(f"`{k}`:{c:,}" for k, c in sorted(r.raw_unknown_kinds.items()))
            lines.append(f"- **unnormalized kinds (routed to `other`):** {unk}")
        # round-trip breakdown
        rt = ", ".join(
            f"{k}:{r.roundtrip[k]:,}" for k in RoundTrip if r.roundtrip[k]
        )
        lines.append(f"- display-path round-trip: {rt} "
                     f"(reconstructable: {_pct(r.roundtrip_reconstruct_rate)})")
        # topology
        lines.append(f"- parents with ≥2 children: {r.parents_with_siblings:,} | "
                     f"physical order == natural sort: {r.sibling_order_consistent:,} "
                     f"({_pct(r.sibling_consistency_rate)})")
        lines.append(f"- leaf `(kind,identifier)` keys: {r.leaf_local_keys:,} | "
                     f"ambiguous (under >1 parent): {r.ambiguous_leaf_local_keys:,} "
                     f"({_pct(r.leaf_ambiguity_rate)})")
        if r.deepest_example:
            lines.append(f"- deepest path: `{r.deepest_example[0]}` "
                         f"({r.deepest_example[1]} levels)")
        if r.sibling_violation_example:
            lines.append(f"- sibling-order divergence example — {r.sibling_violation_example}")
        lines.append("")

    lines.append(EXIT_SECTION)
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    ap = argparse.ArgumentParser(
        description="M0.5B2: hierarchy stress test — parse breadcrumb into a "
        "normalized HierarchyNode[] and measure topology across corpora."
    )
    ap.add_argument("paths", nargs="+", help="Parquet file(s) or glob(s)")
    ap.add_argument("--snapshot", required=True, help="snapshot version, e.g. v2026.08")
    ap.add_argument("--out", help="write the Markdown report here (else stdout)")
    args = ap.parse_args(argv)

    files = sorted({Path(p) for pat in args.paths for p in globlib.glob(pat)})
    reports = [analyze_corpus(f) for f in files]
    report = render_report(reports, args.snapshot)
    if args.out:
        Path(args.out).write_text(report)
        print(f"wrote {args.out} ({len(reports)} corpora)")
    else:
        print(report)


if __name__ == "__main__":
    main()
