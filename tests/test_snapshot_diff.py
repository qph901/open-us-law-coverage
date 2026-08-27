"""M0 snapshot-diff unit tests (review P4): null/empty distinction, deterministic
sampling, and the set-membership claim scope. Hermetic — small in-memory frames."""

from __future__ import annotations

import polars as pl

from open_us_law_coverage.snapshot_diff import _hash_one, diff


def _frame(rows: list[tuple[str, str | None]]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "act_id": [r[0] for r in rows],
            "citation": [r[0] for r in rows],
            "act_status": ["in_force"] * len(rows),
            "text": [r[1] for r in rows],
        },
        schema={"act_id": pl.String, "citation": pl.String, "act_status": pl.String, "text": pl.String},
    )


def test_null_and_empty_hash_differently():
    assert _hash_one(None) != _hash_one("")
    assert _hash_one("") == _hash_one("")


def test_null_to_empty_counts_as_amended():
    old = _frame([("A", None)])
    new = _frame([("A", "")])
    d = diff(old, new)
    assert d["amended"] == 1
    assert d["unchanged"] == 0


def test_both_null_counts_as_unchanged():
    old = _frame([("A", None)])
    new = _frame([("A", None)])
    d = diff(old, new)
    assert d["unchanged"] == 1
    assert d["amended"] == 0


def test_text_change_is_amended_added_removed_by_membership():
    old = _frame([("A", "x"), ("B", "y")])
    new = _frame([("A", "x2"), ("C", "z")])  # A amended, B removed, C added
    d = diff(old, new)
    assert d["amended"] == 1
    assert d["added"] == 1
    assert d["removed"] == 1


def test_amended_examples_are_sorted():
    rows_old = [(f"ID{i:02d}", "old") for i in range(20)]
    rows_new = [(f"ID{i:02d}", "new") for i in range(20)]
    d = diff(_frame(rows_old), _frame(rows_new))
    assert d["amended_examples"] == sorted(d["amended_examples"])
    # deterministic: rerun yields the same sample.
    d2 = diff(_frame(rows_old), _frame(rows_new))
    assert d["amended_examples"] == d2["amended_examples"]


def test_id_reuse_is_not_detected_by_set_membership():
    """Same id, entirely different provision text -> counted as 'amended', and
    removed stays 0. This documents the narrowed claim: set membership cannot
    distinguish a reissue from an in-place amendment."""
    old = _frame([("A", "the old provision")])
    new = _frame([("A", "a completely different provision reissued under A")])
    d = diff(old, new)
    assert d["removed"] == 0
    assert d["amended"] == 1
