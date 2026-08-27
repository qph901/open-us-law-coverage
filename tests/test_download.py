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


def test_moving_ref_is_resolved_to_a_commit_sha():
    for moving in ("main", "dev", "latest", "refs/heads/main"):
        resolved = dl.resolve_revision("v2026.08", moving, resolver=_fake_resolver)
        assert resolved == _FAKE_REFS[moving]
        assert dl._COMMIT_SHA_RE.match(resolved)
        assert resolved != moving  # the raw ref is never returned as-is


def test_full_sha_passes_through():
    assert dl.resolve_revision("v2026.08", _SHA_A, resolver=_fake_resolver) == _SHA_A


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
