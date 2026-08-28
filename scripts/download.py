"""Download and verify Open US Law snapshot files from Hugging Face.

The dataset is gated; export an ``HF_TOKEN`` with gated-repo read access first
(the token is read from the environment). Files land in ``data/<snapshot>/`` and
are checked against the snapshot's ``SHA256SUMS.json``.

**Downloads are pinned to an immutable dataset revision** (M1A.5 review P3): a
snapshot *label* is only a directory name, so fetching from a moving ref like
``main`` could certify newer bytes under an older label and silently corrupt a
cross-snapshot conclusion. Every label must resolve to an immutable commit/tag —
via :data:`SNAPSHOT_REVISIONS` or an explicit ``--revision`` — and the resolved
revision is persisted next to the data.

    HF_TOKEN=hf_... uv run python scripts/download.py \
        us_federal_statutes us_ca_statutes \
        --snapshot v2026.08 --revision <immutable-commit-sha-or-tag>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from huggingface_hub import hf_hub_download

REPO = "vaquill/open-us-law"

# A resolved revision must be an immutable 40-hex commit SHA.
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Snapshot label -> immutable dataset commit/tag. Fill in as snapshots are pinned
# (a full 40-char commit SHA or an immutable tag — never a branch). When a label is
# not listed here, an explicit immutable ``--revision`` is required.
#
# **How a pin is established (NEXT.md D4).** Never transcribe a commit prefix from a
# report — a commit that *introduced* regulations is not proof it is the exact
# revision every staged Parquet came from (later commits can change bytes under one
# label). The pin is established by **checksum-matching**: resolve candidate history
# to full SHAs, and adopt the revision whose ``SHA256SUMS.json`` matches the sha256
# of *every* staged local file (see :func:`find_matching_revision`). If no revision
# matches all staged files, record that limitation explicitly rather than assert a
# false pin, and re-download from a deliberately chosen immutable revision.
SNAPSHOT_REVISIONS: dict[str, str] = {
    # Established by checksum (NEXT.md D4), not transcription: this is the single HF
    # commit for the dataset ("Open US Law v2026.08. Prior snapshots withdrawn.",
    # 2026-08-26), and its SHA256SUMS.json matches the sha256 of all 229 staged
    # Parquet files (verified via find_matching_revision).
    "v2026.08": "16bc9a159faabea4af9db08f1b33832e80e85b2d",
}

# The M0 reconnaissance sample: the commissioned USC corpus, a large and a small
# state statute set, and a constitution set — enough to characterize schema,
# act_id behavior, hierarchy cleanliness, and citation-format variability.
M0_SAMPLE = [
    "us_federal_statutes",
    "us_ca_statutes",
    "us_ak_statutes",
    "us_ak_constitutions",
]

_HASH_CHUNK = 1 << 20  # 1 MiB


def _hf_ref_resolver(ref: str) -> str:
    """Resolve any HF ref (branch, tag, or short/full SHA) to its commit SHA."""
    from huggingface_hub import HfApi

    info = HfApi().repo_info(
        REPO, repo_type="dataset", revision=ref, token=os.environ.get("HF_TOKEN")
    )
    return info.sha


def resolve_revision(
    snapshot: str,
    revision_arg: str | None,
    *,
    resolver: Callable[[str], str] = _hf_ref_resolver,
) -> str:
    """Resolve a snapshot label + ref to an **immutable commit SHA**.

    The supplied ref may be a branch (``main``/``dev``/``refs/heads/main``), a tag
    (``latest``), or a SHA — all of which are ambiguous or moving as *inputs*. We
    resolve it to the concrete commit SHA it points at *now* and record **that**, so
    a moving ref can never be stored as if it were the authoritative revision
    (M1A.5 review P2). Fails if the ref cannot be resolved, if the result is not a
    commit SHA, or if it disagrees with a SHA pinned in ``SNAPSHOT_REVISIONS``.
    """
    pinned = SNAPSHOT_REVISIONS.get(snapshot)
    ref = revision_arg or pinned
    if ref is None:
        raise SystemExit(
            f"no pinned revision for snapshot {snapshot!r}. Pass --revision "
            f"<branch|tag|commit>, or add it to SNAPSHOT_REVISIONS."
        )
    try:
        resolved = resolver(ref)
    except Exception as e:  # network / auth / unknown ref
        raise SystemExit(f"could not resolve revision {ref!r} for {snapshot!r}: {e}")
    if not (resolved and _COMMIT_SHA_RE.match(resolved)):
        raise SystemExit(
            f"revision {ref!r} did not resolve to a commit SHA (got {resolved!r})."
        )
    if pinned and _COMMIT_SHA_RE.match(pinned) and resolved != pinned:
        raise SystemExit(
            f"revision {ref!r} resolved to {resolved}, but snapshot {snapshot!r} is "
            f"pinned to {pinned}."
        )
    return resolved


def _sha256(path: Path) -> str:
    """SHA-256 of a file, streamed in chunks (never ``read_bytes`` — the files are
    large; M1A.5 review P3)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def download(
    names: list[str],
    snapshot: str,
    revision: str,
    out_root: Path,
    *,
    requested_ref: str | None = None,
) -> list[Path]:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN not set. Export a gated-repo read token first.")
    out = out_root / snapshot
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    parquet_files = [f"{n}.parquet" if not n.endswith(".parquet") else n for n in names]
    for f in [*parquet_files, "SHA256SUMS.json"]:
        print(f"downloading {f} @ {revision} ...", flush=True)
        p = hf_hub_download(REPO, f, repo_type="dataset", revision=revision,
                            local_dir=str(out), token=token)
        paths.append(Path(p))
    # Verify BEFORE persisting metadata (NEXT.md D4/C.1): DOWNLOAD_METADATA.json is a
    # certificate that these exact bytes came from this revision, so it must not be
    # written until every requested file has passed its checksum.
    verify(snapshot, out_root, expected=parquet_files)
    write_download_metadata(
        out, snapshot, revision, requested_ref, [Path(p).name for p in paths]
    )
    return paths


def write_download_metadata(
    out: Path,
    snapshot: str,
    revision: str,
    requested_ref: str | None,
    files: list[str],
) -> None:
    """Persist the resolved commit SHA (and requested ref) so the snapshot label stays
    auditable. Written only after :func:`verify` passes."""
    (out / "DOWNLOAD_METADATA.json").write_text(
        json.dumps(
            {
                "snapshot": snapshot,
                "repo": REPO,
                "requested_ref": requested_ref,
                "revision": revision,  # resolved immutable commit SHA
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "files": sorted(files),
            },
            indent=2,
        )
        + "\n"
    )


def verify(snapshot: str, out_root: Path, *, expected: list[str] | None = None) -> list[str]:
    """Check every staged Parquet against ``SHA256SUMS.json``; return the verified names.

    A requested/staged Parquet that is **absent from the manifest is a failure**
    (NEXT.md D4/C.1) — the old code printed ``??`` and continued, which would let an
    uncovered file ride along uncertified. If ``expected`` is given, every name in it
    must also be present and verified.
    """
    out = out_root / snapshot
    sums = json.loads((out / "SHA256SUMS.json").read_text())
    by_file = {e["file"]: e for e in sums}
    verified: list[str] = []
    for p in sorted(out.glob("*.parquet")):
        entry = by_file.get(p.name)
        if entry is None:
            raise SystemExit(
                f"{p.name} is not in SHA256SUMS.json — refusing to certify a file the "
                f"manifest does not cover"
            )
        if _sha256(p) != entry["sha256"]:
            print(f"BAD {p.name}", flush=True)
            raise SystemExit(f"checksum mismatch for {p.name}")
        print(f"OK  {p.name}  rows={entry.get('rows')}", flush=True)
        verified.append(p.name)
    if expected:
        missing = [f for f in expected if f not in verified]
        if missing:
            raise SystemExit(f"expected files missing after verify: {missing}")
    return verified


def load_manifest(path: Path) -> dict[str, str]:
    """A ``SHA256SUMS.json`` file reduced to ``{filename: sha256}``."""
    return {e["file"]: e["sha256"] for e in json.loads(path.read_text())}


def manifest_matches_local(
    manifest: dict[str, str], local: dict[str, str]
) -> bool:
    """True iff every staged local file appears in ``manifest`` with a matching sha256.

    The staged set may be a subset of the full snapshot, so extra manifest entries are
    fine; a staged file that is missing from the manifest, or whose sha disagrees, is
    a non-match.
    """
    return bool(local) and all(manifest.get(name) == sha for name, sha in local.items())


def find_matching_revision(
    snapshot: str,
    candidate_refs: list[str],
    out_root: Path,
    *,
    resolver: Callable[[str], str] = _hf_ref_resolver,
    manifest_fetcher: Callable[[str], dict[str, str]],
) -> str | None:
    """Establish the snapshot pin by checksum (NEXT.md D4).

    For each candidate ref: resolve it to a full commit SHA, fetch that revision's
    ``SHA256SUMS.json``, and compare it against the sha256 of every staged local file.
    The first revision whose manifest matches all staged files is the pin. Returns
    ``None`` if none matches — the caller must then record the limitation explicitly
    rather than assert a false pin.
    """
    out = out_root / snapshot
    local = {p.name: _sha256(p) for p in sorted(out.glob("*.parquet"))}
    if not local:
        raise SystemExit(f"no staged Parquet under {out} to match a revision against")
    for ref in candidate_refs:
        sha = resolver(ref)
        if not (sha and _COMMIT_SHA_RE.match(sha)):
            continue
        if manifest_matches_local(manifest_fetcher(sha), local):
            return sha
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="*", default=M0_SAMPLE,
                    help="File stems (default: the M0 reconnaissance sample).")
    ap.add_argument("--snapshot", default="v2026.08")
    ap.add_argument("--revision", default=None,
                    help="Dataset ref (branch, tag, or commit) to download. It is "
                         "resolved to an immutable commit SHA, which is what gets "
                         "recorded. Required unless the snapshot is in SNAPSHOT_REVISIONS.")
    ap.add_argument("--out", type=Path, default=Path("data"))
    args = ap.parse_args()
    requested_ref = args.revision or SNAPSHOT_REVISIONS.get(args.snapshot)
    revision = resolve_revision(args.snapshot, args.revision)
    if requested_ref != revision:
        print(f"resolved ref {requested_ref!r} -> commit {revision}", flush=True)
    # download() verifies every file against SHA256SUMS.json and writes
    # DOWNLOAD_METADATA.json only if that passes (NEXT.md D4/C.1).
    download(args.names or M0_SAMPLE, args.snapshot, revision, args.out,
             requested_ref=requested_ref)


if __name__ == "__main__":
    main()
