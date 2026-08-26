"""M0.5B2 acceptance — the breadcrumb hierarchy parser + topology helpers.

Hermetic: the breadcrumb strings below are the exact shapes observed in the real
corpora (CA variable-order codes, TX flat, OH agency/rule, DE unnumbered group
containers), so the parser is exercised on the adversarial cases without the
gated dataset.
"""

from __future__ import annotations

import json

import pytest

from open_us_law_coverage.hierarchy import (
    HierarchyKind,
    HierarchySource,
    RoundTrip,
    natural_key,
    normalize_kind,
    parse_breadcrumb,
    roundtrip_status,
    split_display_path,
    to_structural_path,
)

# Real-shape fixtures ------------------------------------------------------

CA = json.dumps([
    {"type": "code", "num": "bpc", "label": "Code bpc", "name": ""},
    {"type": "division", "num": "2", "label": "Division 2", "name": ""},
    {"type": "chapter", "num": "6.6", "label": "Chapter 6.6", "name": ""},
    {"type": "article", "num": "3", "label": "Article 3", "name": ""},
    {"type": "section", "num": "2943", "label": "Section 2943", "name": ""},
])
CA_DISPLAY = "California Code / Code bpc / Division 2 / Chapter 6.6 / Article 3 / Section 2943"

TX = json.dumps([
    {"type": "code", "num": "al", "label": "Code al", "name": ""},
    {"type": "chapter", "num": "25", "label": "Chapter 25", "name": ""},
    {"type": "section", "num": "25.01", "label": "Section 25.01", "name": ""},
])

# DE: unnumbered container ``group`` (num == "") + a title with a name that
# display_path appends.
DE = json.dumps([
    {"type": "title", "num": "8", "label": "Title 8", "name": "Public Information (FOIA)"},
    {"type": "group", "num": "", "label": "Department of Labor, Office of the Secretary",
     "name": "Department of Labor, Office of the Secretary"},
    {"type": "regulation", "num": "800", "label": "8 DE Admin. Code 800",
     "name": "Policies and Procedures Regarding FOIA Requests"},
])
DE_DISPLAY = ("Delaware Administrative Code / Title 8 Public Information (FOIA) / "
              "Department of Labor, Office of the Secretary / 8 DE Admin. Code 800")


def test_parse_depth_and_ordinal():
    nodes = parse_breadcrumb(CA)
    assert [n.ordinal for n in nodes] == [0, 1, 2, 3, 4]
    assert [n.kind for n in nodes] == [
        HierarchyKind.CODE, HierarchyKind.DIVISION, HierarchyKind.CHAPTER,
        HierarchyKind.ARTICLE, HierarchyKind.SECTION,
    ]
    assert [n.identifier for n in nodes] == ["bpc", "2", "6.6", "3", "2943"]
    assert all(n.source == HierarchySource.BREADCRUMB for n in nodes)
    assert all(n.confidence == 1.0 for n in nodes)


def test_variable_kind_order_is_not_forced():
    # TX has no division/article and title is absent entirely — parser must not
    # impose a title/chapter/section shape.
    nodes = parse_breadcrumb(TX)
    assert [n.kind for n in nodes] == [
        HierarchyKind.CODE, HierarchyKind.CHAPTER, HierarchyKind.SECTION
    ]


def test_unnumbered_container_abstains_on_identifier():
    nodes = parse_breadcrumb(DE)
    group = nodes[1]
    assert group.kind == HierarchyKind.GROUP
    assert group.identifier is None            # never fabricated
    assert group.confidence < 1.0              # reduced, an explicit abstention
    assert group.label  # still has a usable label


def test_unknown_kind_routes_to_other_with_raw_preserved():
    kind, conf, raw = normalize_kind("titlette")
    assert kind == HierarchyKind.OTHER
    assert raw == "titlette"
    assert conf < 1.0
    nodes = parse_breadcrumb(json.dumps([{"type": "titlette", "num": "1", "label": "X"}]))
    assert nodes[0].kind == HierarchyKind.OTHER
    assert nodes[0].raw_kind == "titlette"


@pytest.mark.parametrize("bad", [None, "", "   ", "not json", "{}", "[1, 2, 3]", "null"])
def test_malformed_breadcrumb_yields_empty_path(bad):
    assert parse_breadcrumb(bad) == []


def test_roundtrip_exact_when_labels_match():
    assert roundtrip_status(parse_breadcrumb(CA), CA_DISPLAY) == RoundTrip.EXACT


def test_roundtrip_prefix_when_display_appends_name():
    # DE display_path appends the title/group name to the label -> prefix, not exact.
    assert roundtrip_status(parse_breadcrumb(DE), DE_DISPLAY) == RoundTrip.PREFIX


def test_roundtrip_length_mismatch():
    assert roundtrip_status(parse_breadcrumb(TX), "TX Code / Code al") == RoundTrip.LENGTH_MISMATCH


def test_split_display_path_drops_root():
    root, segs = split_display_path(CA_DISPLAY)
    assert root == "California Code"
    assert segs[0] == "Code bpc" and segs[-1] == "Section 2943"


def test_natural_key_orders_dotted_numbers():
    ids = ["6.10", "6.7", "6.6", "6.100", "6.9"]
    assert sorted(ids, key=natural_key) == ["6.6", "6.7", "6.9", "6.10", "6.100"]


def test_natural_key_none_sorts_last():
    assert sorted(["5", None, "1"], key=natural_key) == ["1", "5", None]


# StructuralPath ------------------------------------------------------------

def test_structural_path_from_nodes():
    sp = to_structural_path(parse_breadcrumb(CA))
    assert sp.depth == 5
    assert sp.leaf == ("section", "2943")
    assert sp.render() == "code:bpc/division:2/chapter:6.6/article:3/section:2943"


def test_structural_path_unnumbered_falls_back_to_label():
    # DE group has num "" -> the key uses the label so the path stays well-defined.
    sp = to_structural_path(parse_breadcrumb(DE))
    kinds = [k for k, _ in sp.steps]
    assert kinds == ["title", "group", "regulation"]
    assert sp.steps[1] == ("group", "Department of Labor, Office of the Secretary")


def test_structural_path_distinguishes_same_leaf_under_different_parents():
    # a bare leaf id is ambiguous; the absolute path is not.
    a = to_structural_path(parse_breadcrumb(json.dumps([
        {"type": "chapter", "num": "1", "label": "Chapter 1"},
        {"type": "section", "num": "5", "label": "Section 5"},
    ])))
    b = to_structural_path(parse_breadcrumb(json.dumps([
        {"type": "chapter", "num": "2", "label": "Chapter 2"},
        {"type": "section", "num": "5", "label": "Section 5"},
    ])))
    assert a.leaf == b.leaf == ("section", "5")
    assert a.render() != b.render()
