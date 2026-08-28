"""Unit tests for the download revision pinning (M1A.5 review P2/P3).

Hermetic: a fake resolver stands in for the Hugging Face API, so no network/token
is needed. The point under test is that a *moving* ref is resolved to an immutable
commit SHA and that SHA — never the raw ref — is what the tool treats as resolved.
"""

from __future__ import annotations

import pytest

import scripts.download as dl

_SHA_A = "a" * 40
_SHA_B = "b" * 40

_FAKE_REFS = {
    "main": _SHA_A,
    "dev": _SHA_B,
    "latest": _SHA_A,
    "refs/heads/main": _SHA_A,
    _SHA_A: _SHA_A,  # a real sha resolves to itself
}


def _fake_resolver(ref: str) -> str:
    return _FAKE_REFS[ref]


# An unpinned label, so these exercise resolution mechanics independent of the real
# SNAPSHOT_REVISIONS pin (which would otherwise reject a conflicting fake sha).
_UNPINNED = "v2099.01"


def test_moving_ref_is_resolved_to_a_commit_sha():
    for moving in ("main", "dev", "latest", "refs/heads/main"):
        resolved = dl.resolve_revision(_UNPINNED, moving, resolver=_fake_resolver)
        assert resolved == _FAKE_REFS[moving]
        assert dl._COMMIT_SHA_RE.match(resolved)
        assert resolved != moving  # the raw ref is never returned as-is


def test_full_sha_passes_through():
    assert dl.resolve_revision(_UNPINNED, _SHA_A, resolver=_fake_resolver) == _SHA_A


def test_non_sha_resolution_is_rejected():
    with pytest.raises(SystemExit):
        dl.resolve_revision("v2026.08", "main", resolver=lambda ref: "not-a-sha")


def test_unresolvable_ref_fails_loudly():
    def _boom(ref):
        raise RuntimeError("unknown ref")

    with pytest.raises(SystemExit):
        dl.resolve_revision("v2026.08", "nope", resolver=_boom)


def test_missing_ref_requires_explicit_revision():
    with pytest.raises(SystemExit):
        dl.resolve_revision("v2099.01", None, resolver=_fake_resolver)


def test_resolution_conflicting_with_pin_is_rejected(monkeypatch):
    monkeypatch.setitem(dl.SNAPSHOT_REVISIONS, "v2026.08", _SHA_A)
    # requesting a ref that resolves to a *different* sha than the pin -> error.
    with pytest.raises(SystemExit):
        dl.resolve_revision("v2026.08", "dev", resolver=_fake_resolver)
    # requesting one that resolves to the pinned sha is fine.
    assert dl.resolve_revision("v2026.08", "main", resolver=_fake_resolver) == _SHA_A


def test_pinned_snapshot_resolves_without_explicit_arg(monkeypatch):
    monkeypatch.setitem(dl.SNAPSHOT_REVISIONS, "v2026.08", _SHA_A)
    assert dl.resolve_revision("v2026.08", None, resolver=_fake_resolver) == _SHA_A


def test_v2026_08_is_pinned_to_an_immutable_commit_sha():
    """NEXT.md D4: the snapshot is pinned to a full commit SHA (established by
    checksum-matching all staged files against the commit's SHA256SUMS.json)."""
    pin = dl.SNAPSHOT_REVISIONS.get("v2026.08")
    assert pin is not None and dl._COMMIT_SHA_RE.match(pin)
    # a real-sha resolver (the pin resolves to itself) agrees with the pin.
    assert dl.resolve_revision("v2026.08", None, resolver=lambda r: pin) == pin


# --- NEXT.md D4 / C.1: verify() hardening + checksum-based pin ----------------

import hashlib
import json


def _stage(tmp_path, snapshot, files, manifest_entries):
    out = tmp_path / snapshot
    out.mkdir(parents=True)
    for name, content in files.items():
        (out / name).write_bytes(content)
    (out / "SHA256SUMS.json").write_text(json.dumps(manifest_entries))
    return out


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def test_verify_passes_and_returns_verified_names(tmp_path):
    a, b = b"parquet-a", b"parquet-b"
    _stage(
        tmp_path, "v2026.08",
        {"us_x_statutes.parquet": a, "us_y_statutes.parquet": b},
        [
            {"file": "us_x_statutes.parquet", "sha256": _sha(a), "rows": 1},
            {"file": "us_y_statutes.parquet", "sha256": _sha(b), "rows": 2},
        ],
    )
    verified = dl.verify("v2026.08", tmp_path)
    assert verified == ["us_x_statutes.parquet", "us_y_statutes.parquet"]


def test_verify_fails_on_file_absent_from_manifest(tmp_path):
    """The core D4/C.1 fix: an uncovered staged file is a failure, not a `??` skip."""
    a = b"parquet-a"
    _stage(
        tmp_path, "v2026.08",
        {"us_x_statutes.parquet": a, "us_orphan.parquet": b"orphan"},
        [{"file": "us_x_statutes.parquet", "sha256": _sha(a)}],
    )
    with pytest.raises(SystemExit, match="not in SHA256SUMS"):
        dl.verify("v2026.08", tmp_path)


def test_verify_fails_on_checksum_mismatch(tmp_path):
    _stage(
        tmp_path, "v2026.08",
        {"us_x_statutes.parquet": b"actual-bytes"},
        [{"file": "us_x_statutes.parquet", "sha256": _sha(b"different-bytes")}],
    )
    with pytest.raises(SystemExit, match="checksum mismatch"):
        dl.verify("v2026.08", tmp_path)


def test_verify_fails_when_expected_file_missing(tmp_path):
    a = b"parquet-a"
    _stage(
        tmp_path, "v2026.08",
        {"us_x_statutes.parquet": a},
        [{"file": "us_x_statutes.parquet", "sha256": _sha(a)}],
    )
    with pytest.raises(SystemExit, match="expected files missing"):
        dl.verify("v2026.08", tmp_path, expected=["us_x_statutes.parquet", "us_missing.parquet"])


def test_find_matching_revision_picks_the_revision_whose_manifest_matches(tmp_path):
    a, b = b"parquet-a", b"parquet-b"
    _stage(
        tmp_path, "v2026.08",
        {"us_x_statutes.parquet": a, "us_y_statutes.parquet": b},
        [],  # local SHA256SUMS.json unused by find_matching_revision
    )
    manifests = {
        "c" * 40: {"us_x_statutes.parquet": _sha(a), "us_y_statutes.parquet": _sha(b)},
        "d" * 40: {"us_x_statutes.parquet": _sha(a), "us_y_statutes.parquet": _sha(b"stale")},
    }
    match = dl.find_matching_revision(
        "v2026.08", ["d_ref", "c_ref"], tmp_path,
        resolver=lambda r: {"c_ref": "c" * 40, "d_ref": "d" * 40}[r],
        manifest_fetcher=lambda sha: manifests[sha],
    )
    assert match == "c" * 40  # only c's manifest matches every staged file


def test_find_matching_revision_returns_none_when_no_match(tmp_path):
    a = b"parquet-a"
    _stage(tmp_path, "v2026.08", {"us_x_statutes.parquet": a}, [])
    match = dl.find_matching_revision(
        "v2026.08", ["ref"], tmp_path,
        resolver=lambda r: "e" * 40,
        manifest_fetcher=lambda sha: {"us_x_statutes.parquet": _sha(b"nope")},
    )
    assert match is None


def test_manifest_matches_local_allows_manifest_superset():
    local = {"a.parquet": "h1"}
    manifest = {"a.parquet": "h1", "b.parquet": "h2"}  # extra entries are fine
    assert dl.manifest_matches_local(manifest, local)
    assert not dl.manifest_matches_local({"a.parquet": "other"}, local)
    assert not dl.manifest_matches_local({}, local)
