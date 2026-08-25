"""Download and verify Open US Law snapshot files from Hugging Face.

The dataset is gated; export an ``HF_TOKEN`` with gated-repo read access first
(the token is read from the environment). Files land in ``data/<snapshot>/`` and
are checked against the snapshot's ``SHA256SUMS.json``.

    HF_TOKEN=hf_... uv run python scripts/download.py \
        us_federal_statutes us_ca_statutes --snapshot v2026.08
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from huggingface_hub import hf_hub_download

REPO = "vaquill/open-us-law"

# The M0 reconnaissance sample: the commissioned USC corpus, a large and a small
# state statute set, and a constitution set — enough to characterize schema,
# act_id behavior, hierarchy cleanliness, and citation-format variability.
M0_SAMPLE = [
    "us_federal_statutes",
    "us_ca_statutes",
    "us_ak_statutes",
    "us_ak_constitutions",
]


def download(names: list[str], snapshot: str, out_root: Path) -> list[Path]:
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN not set. Export a gated-repo read token first.")
    out = out_root / snapshot
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    files = [f"{n}.parquet" if not n.endswith(".parquet") else n for n in names]
    files.append("SHA256SUMS.json")
    for f in files:
        print(f"downloading {f} ...", flush=True)
        p = hf_hub_download(REPO, f, repo_type="dataset", revision="main",
                            local_dir=str(out), token=token)
        paths.append(Path(p))
    return paths


def verify(snapshot: str, out_root: Path) -> None:
    out = out_root / snapshot
    sums = json.loads((out / "SHA256SUMS.json").read_text())
    by_file = {e["file"]: e for e in sums}
    for p in sorted(out.glob("*.parquet")):
        entry = by_file.get(p.name)
        if not entry:
            print(f"?? {p.name}: not in SHA256SUMS")
            continue
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        ok = h == entry["sha256"]
        print(f"{'OK ' if ok else 'BAD'} {p.name}  rows={entry.get('rows')}")
        if not ok:
            raise SystemExit(f"checksum mismatch for {p.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("names", nargs="*", default=M0_SAMPLE,
                    help="File stems (default: the M0 reconnaissance sample).")
    ap.add_argument("--snapshot", default="v2026.08")
    ap.add_argument("--out", type=Path, default=Path("data"))
    args = ap.parse_args()
    download(args.names or M0_SAMPLE, args.snapshot, args.out)
    verify(args.snapshot, args.out)


if __name__ == "__main__":
    main()
