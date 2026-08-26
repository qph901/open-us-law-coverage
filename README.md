# Open US Law — Citation Parser & Resolver

A citation detection / parsing / normalization / resolution subsystem over the
[`vaquill/open-us-law`](https://huggingface.co/datasets/vaquill/open-us-law)
dataset (snapshot **v2026.08**), commissioned on the US Code. See
[PROPOSAL.md](PROPOSAL.md) for the full design and milestones.

## Status

- **M0 — Dataset reconnaissance: complete.** Report at
  [reports/M0_recon.md](reports/M0_recon.md). Answers the proposal's `act_id`
  behavior, crosswalk-field, hierarchy-cleanliness, and citation-format
  questions against real Parquet (deterministic renumber lineage from text;
  breadcrumb-based hierarchy; pre-extracted USC cross-references).
- **M0 — Full-snapshot reconnaissance: complete.** Report at
  [reports/M0_full_snapshot.md](reports/M0_full_snapshot.md). The recon harness
  run over all **229 files / 2,978,617 rows** of `v2026.08`: one uniform
  24-column schema everywhere, no crosswalk column anywhere, `act_id` 100%
  populated across every corpus (but **not unique within the federal
  regulations file** — a Tier-1 caveat), and 10,395 rows carrying a
  disposition status that routes to lineage inference. Confirms the sample-set
  findings hold at full scale.
- **M0 — `act_id` stability across snapshots: answered.** Report at
  [reports/M0_act_id_stability.md](reports/M0_act_id_stability.md). Diffing
  `v2026.07` → `v2026.08` across federal/CA/AK: **no act_id was ever removed or
  reissued**, and thousands survive text amendment → `act_id` is a safe Tier-1
  identity seed. Key caveat: the USC `text` field bundles a volatile
  editorial-notes apparatus, so `text_hash` over raw `text` overstates real
  amendment (~48% of USC "changed", almost all editorial-note growth). Hash the
  operative body separately.
- **M0.5A — Identity-collision analysis: complete.** Report at
  [reports/M0.5A_identity_collisions.md](reports/M0.5A_identity_collisions.md).
  Collisions are **entirely a regulations-corpus phenomenon** (7 of 229 files;
  every statute/constitution `act_id` is unique). In `us_federal_regulations`
  the file mixes two namespaces: `CFR_*` (codified sections, ~nearly unique) and
  `FR_*` (Federal Register documents split into text segments — 99.99% of the
  167k collision rows). State-regulation collisions are mostly literal duplicate
  rows (Ohio: 539/555 groups byte-identical). Yields a per-corpus
  `SourceIdentityStrategy`: `source_id = (state, corpus, act_id, segment_ordinal)`
  for regulations, `legal_id = (state, corpus, act_id)` at document/section
  granularity, duplicate rows flagged not silently deduped.
- **M0.5A.1 — Collision-provenance + segment-order spike: complete.** Report at
  [reports/M0.5A1_segment_provenance.md](reports/M0.5A1_segment_provenance.md).
  Two findings reshape M0.5A. (1) The v2026.07↔v2026.08 comparison A.1 called for
  has an **empty domain** — regulations were *introduced* in v2026.08, so exit
  questions on cross-snapshot segment/order stability are **untestable** until a
  second regulations-bearing snapshot ships. (2) The `FR_*` distinct-text
  collisions are **co-numbered distinct documents, not ordered segments**: their
  rows are physically scattered, the continuation rate is ≈0%, and ≈96% of groups
  restart with the same agency preamble — so concatenating them reconstructs
  nothing. Conclusion: `segment_ordinal` is **snapshot-observed physical row
  order** (no source-defined ordinal exists), a lossless row discriminator only,
  never a reading order. The source-identity contract may freeze with that caveat.
- **M1A — immutable `CanonicalSourceRecord` core: complete.** Lossless
  serializer in
  [`src/open_us_law_coverage/source_record.py`](src/open_us_law_coverage/source_record.py),
  with the golden-fixture acceptance suite in
  [`tests/test_source_record.py`](tests/test_source_record.py) (21 invariants,
  incl. the **boundary test**: a simulated identity/anatomy/hierarchy/quality
  parser improvement requires *zero* changes to any source record). Preserves all
  24 columns verbatim (null stays null), holds `raw_text` byte-for-byte, and
  derives `source_record_id` from physical coordinates only —
  `(snapshot_version, source_file_checksum, physical_row_ordinal)` — never from
  content or citation. The reader stays row-group-bounded, so a full-snapshot
  pass is safe on the 11 GB federal regulations `text` column. Run:
  `uv run pytest`.
- **M1A.5 — shared derived-artifact foundation: scaffolded.** The
  interpretation-layer contracts in
  [`src/open_us_law_coverage/derived/`](src/open_us_law_coverage/derived/):
  `DerivedArtifactProvenance` as a multi-input DAG (content-addressed
  `artifact_id`, `generated_at` excluded), `SourceIdentityAnnotation` (groups
  only, never composes), and the first producers — deterministic
  `DocumentClassificationAnnotation`, `duplicate_row`-only `QualityAnnotation`,
  and `trivial_single_record_v1` `SourceDocumentAssembly`. The headline
  **durable-FK test** proves identity/assembly v1↔v2 coexist over the same
  records and no artifact is keyed by `source_identity_key`. Concrete identity
  strategies and the CFR multi-row composer land later (CFR path).
- **M0.5B2 — Hierarchy stress test: complete.** Report at
  [reports/M0.5B2_hierarchy.md](reports/M0.5B2_hierarchy.md). A single
  `breadcrumb`-driven parser normalizes CA statutes (variable code/division/part/
  title ordering), TX statutes (flat, `title_number` 100% null), OH regulations
  (agency/chapter/rule), and DE regulations (title/group/regulation with
  *unnumbered container* nodes) into one `HierarchyNode[]` shape — **no interface
  change forced**. Topology tested, not just coverage: acyclicity and proper-tree
  assembly are clean, but **bare-identifier LOCAL resolution is unsafe** (12–26%
  of leaf `(kind,identifier)` keys sit under >1 parent) and **sibling order is
  only partly recoverable** from physical row order (8–90% by corpus), so
  RELATIVE resolution must operate on the absolute path and abstain on the rest.
- **M0.5B3 — CA abstraction-falsification probe: complete.** Report at
  [reports/M0.5B3_ca_abstraction.md](reports/M0.5B3_ca_abstraction.md). Runs every
  built artifact type over the full 161,566-row CA statutes corpus: **zero
  interface changes forced** — identity is 1:1 (`act_id` and `StructuralPath` both
  100% unique), classification/hierarchy/assembly all represent CA without
  distortion. Two requirements captured as *producer/taxonomy* notes: `duplicate_row`
  must be scoped to the identity group (CA has 7,642 rows byte-identical across
  *distinct* provisions — content ≠ identity), and anatomy (B1) must carry a
  leading `[Repealed … and added by Stats. …]` history bracket and not trust
  `act_status`. **M0.5B1 (needs USLM) / CFR-A1 (needs eCFR): not started.**

## Setup

The dataset is **gated** on Hugging Face. A human must accept the dataset terms
and provide a read token:

```bash
export HF_TOKEN=hf_...   # a token with gated-repo read access
```

Install deps and download the M0 sample (verified against `SHA256SUMS.json`):

```bash
uv sync
uv run python scripts/download.py            # M0 sample → data/v2026.08/
```

## Reproduce the M0 report

```bash
uv run python -m open_us_law_coverage.recon \
  data/v2026.08/*.parquet --snapshot v2026.08 --out reports/M0_recon.md
```

The recon harness accepts any file glob, so it can be pointed at the full
229-file snapshot once downloaded.

## Layout

- `src/open_us_law_coverage/recon.py` — M0 reconnaissance harness.
- `src/open_us_law_coverage/identity_collisions.py` — M0.5A `act_id`-collision
  analysis (DuckDB, spills to disk so the 11 GB federal `text` column is safe).
- `src/open_us_law_coverage/segment_provenance.py` — M0.5A.1 collision-provenance
  + segment-order spike (DuckDB `file_row_number`).
- `src/open_us_law_coverage/source_record.py` — M1A immutable
  `CanonicalSourceRecord` core (lossless serializer + boundary-enforcing model).
- `src/open_us_law_coverage/derived/` — M1A.5 shared derived-artifact foundation
  (provenance DAG + identity/classification/quality/assembly contracts and their
  first producers).
- `src/open_us_law_coverage/hierarchy.py` — M0.5B2 hierarchy stress test
  (breadcrumb → normalized `HierarchyNode[]` / `StructuralPath` + topology report).
- `src/open_us_law_coverage/ca_probe.py` — M0.5B3 CA abstraction-falsification
  probe (runs the built artifact types over CA; emits the interface-change list).
- `tests/` — golden-fixture acceptance suite (`uv run pytest`).
- `scripts/download.py` — gated download + SHA-256 verification.
- `reports/` — generated reports (committed).
- `data/` — downloaded snapshots (gitignored; reproduce via `scripts/download.py`).
