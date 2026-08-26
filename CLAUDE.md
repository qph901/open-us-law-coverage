# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **citation detection / parsing / normalization / resolution** subsystem over the gated
`vaquill/open-us-law` dataset (snapshot **v2026.08**), commissioned on the US Code. It is the
deliberate *foundation* of a legal RAG system — the goal is to reliably identify what law a
citation refers to, with an auditable explanation, **before** any embeddings.

**`PROPOSAL.md` is the source of truth for scope, design, and milestones — read it before making
design decisions.** Milestone status lives in `README.md`. As of this writing M0 (dataset
reconnaissance), M0.5A (identity-collision analysis), M0.5A.1 (collision-provenance +
segment-order spike), and **M1A (the immutable `CanonicalSourceRecord` core)** are complete;
the source-identity contract has frozen with the *snapshot-observed ordinal* caveat from M0.5A.1.
**M1A.5** (the shared derived-artifact foundation) is **scaffolded** — the `DerivedArtifactProvenance`
multi-input DAG + `SourceIdentityAnnotation`(shape) + `DocumentClassificationAnnotation`(deterministic)
+ `QualityAnnotation`(duplicate-only) + `SourceDocumentAssembly`(`trivial_single_record_v1`) + the
durable-FK test all live in `src/open_us_law_coverage/derived/`; the concrete `SourceIdentityStrategy`
producers and the CFR multi-row composer are **not** built yet. **M0.5B2** (hierarchy stress test) is
**complete** (`reports/M0.5B2_hierarchy.md`). Remaining before the M1B semantic freeze: the concrete
identity strategies, the **CFR assembly layer** (CFR-A1 eCFR-validated commissioning → CFR-A2
`cfr_source_assembly_v1` — needs human-staged edition-pinned eCFR), and the other **M0.5B** spikes
(B1 anatomy — needs edition-pinned USLM; B3 CA abstraction probe), then M1B → M0.5C. Assembly precedes
anatomy in the layer order; interfaces co-land in M1A.5 but the assembly *producer* runs after identity
groups the members (see PROPOSAL.md "Settled architecture", "Milestones", "Design decisions", and
"First action for Claude Code").

## Environment & commands

Package manager is **uv** (Python ≥3.12). There is no `pip`/`python` on PATH — always go through uv.

```bash
uv sync                                      # install deps into .venv
uv run python -m open_us_law_coverage.recon  <glob> --snapshot v2026.08 --out reports/<name>.md
uv run python -m open_us_law_coverage.snapshot_diff --old <old.parquet> --new <new.parquet> \
    --old-label v2026.07 --new-label v2026.08 --out reports/M0_act_id_stability.md
```

The dataset is **gated** on Hugging Face; downloads need `HF_TOKEN` (a gated-repo read token) in the
environment. `scripts/download.py` reads it from the env and verifies every file against the
snapshot's `SHA256SUMS.json`:

```bash
HF_TOKEN=hf_... uv run python scripts/download.py            # M0 sample -> data/v2026.08/
```

> If `HF_TOKEN` lives in `~/.bashrc`, note it may be behind the interactive-shell early-return, so a
> non-interactive `uv run` won't see it — export it explicitly in the command when in doubt.

Downloaded snapshots live under `data/` and are **gitignored** (large + gated). Reports under
`reports/` **are** committed. The test suite starts at **M1A**: `uv run pytest` runs the
golden-fixture acceptance suite in `tests/` (pytest is a dev dependency; config in
`pyproject.toml`). The M0/M0.5 harnesses have no tests of their own — their contract is a
byte-stable committed report; don't invent test commands beyond `uv run pytest`.

## Architecture

Two standalone reconnaissance harnesses, each pairing with a committed report. Both read Parquet and
emit Markdown; neither has runtime dependencies on the other:

- `src/open_us_law_coverage/recon.py` → `reports/M0_recon.md` (per-file detail, ≤8 files) and
  `reports/M0_full_snapshot.md` (scalable cross-file summary, auto-selected for >8 files). One
  `analyze_file` per Parquet file produces a `FileReport`; `render_report` / `render_summary` format
  the list. Accepts any file glob, so the same code runs on the 4-file sample or the full 229-file
  snapshot.
- `src/open_us_law_coverage/snapshot_diff.py` → `reports/M0_act_id_stability.md`. Diffs the *same*
  corpus file across two snapshots to answer the one question a single snapshot can't:
  does `act_id` survive text-only amendment (vs. change on renumber/transfer)?
- `src/open_us_law_coverage/identity_collisions.py` → `reports/M0.5A_identity_collisions.md` (M0.5A).
  Enumerates every corpus where `act_id` repeats and classifies each collision group by *phenomenon*
  (ETL duplicate row vs. multi-segment document vs. shared namespace) **before** recommending a key.
  Built on **DuckDB**, not the polars/pyarrow harness: the exact-duplicate test needs a
  `COUNT(DISTINCT md5(text))`-per-group aggregate over the 11 GB federal `text` column, and DuckDB
  streams it in vectors + spills to `--temp-dir` under `--memory-limit`, where pyarrow
  `read_row_group` OOM-kills the box (see below). Regenerate with:

  ```bash
  uv run python -m open_us_law_coverage.identity_collisions data/v2026.08_full/*.parquet \
      --snapshot v2026.08 --out reports/M0.5A_identity_collisions.md \
      --memory-limit 4GB --temp-dir /path/to/scratch/ddspill
  ```

  Examples use `min(act_id)` (not `any_value`) so the report is byte-stable across reruns. The
  recommended `SourceIdentityStrategy` prose lives in `STRATEGY_SECTION` in the module (embedded, not
  hand-edited into the report) so the report regenerates verbatim.
- `src/open_us_law_coverage/segment_provenance.py` → `reports/M0.5A1_segment_provenance.md` (M0.5A.1).
  The collision-provenance + segment-order spike. Also DuckDB-based, and it adds `file_row_number=true`
  to `read_parquet` to recover a stable within-file **physical row ordinal** without materializing a
  row-group. Two load-bearing results it established (design against these): (1) the v2026.07↔v2026.08
  comparison PROPOSAL asked for has an **empty domain** — regulations are new in v2026.08, so
  cross-snapshot segment/order stability is **untestable** until a second regulations snapshot; (2)
  `FR_*` distinct-text collisions are **co-numbered distinct documents, not ordered segments**
  (scattered rows, ≈0% mid-sentence continuation, ≈96% share an agency preamble) — so `segment_ordinal`
  is *snapshot-observed physical row order* only, never a reading order, and FR full-text concatenation
  is invalid. Exit-question verdicts live in `EXIT_SECTION` (embedded, qualitative prose so it never
  drifts from the computed tables). Regenerate with:

  ```bash
  uv run python -m open_us_law_coverage.segment_provenance data/v2026.08_full/*_regulations.parquet \
      --snapshot v2026.08 --out reports/M0.5A1_segment_provenance.md \
      --memory-limit 4GB --temp-dir /path/to/scratch/ddspill
  ```
- `src/open_us_law_coverage/source_record.py` → `tests/test_source_record.py` (M1A). The immutable,
  lossless `CanonicalSourceRecord` core — **not** a report harness; its deliverable is the model +
  the golden-fixture acceptance suite. `CanonicalSourceRecord` is a `@dataclass(frozen=True)` with
  `original_columns` as a `MappingProxyType`, so neither the record nor its preserved columns can be
  mutated (this is what makes the boundary test enforceable). `source_record_id =
  compute_source_record_id(snapshot_version, source_file_checksum, physical_row_ordinal)` and
  `raw_text_hash = compute_raw_text_hash(raw_text)` are **pure module functions** so tests recompute
  identity independently; the id derives from physical coordinates only (never content/citation), and
  the hash is over **raw** `text` bytes (never normalized/operative). `iter_source_records` is the
  streaming reader (row-group-bounded per the OOM invariant below — one row-group of `text` in flight,
  pool released between groups); `read_source_records` is the eager wrapper for small/fixture files
  only. It validates the 24-column schema (`SchemaMismatchError`) and assigns `physical_row_ordinal`
  by an insertion-preserving read (row groups in file order, rows in row-group order). The tests are
  hermetic — `tests/conftest.py` synthesizes a multi-row-group Parquet (unicode, null text, null
  metadata, empty string, byte-identical twins); `test_real_sample_roundtrip` additionally checks the
  committed `data/v2026.08/us_ak_constitutions.parquet` when present (skips otherwise). A cheap
  no-`text`-scan snapshot manifest: `uv run python -m open_us_law_coverage.source_record
  data/v2026.08/*.parquet --snapshot v2026.08`.
- `src/open_us_law_coverage/derived/` (M1A.5) — the shared derived-artifact foundation, on the
  *interpretation* side of the versioned boundary (so rebuilding any of it has **zero** effect on
  `source_record_id`/`raw_text_hash`). Not a report harness; its deliverable is the contracts + the
  golden-fixture suites (`tests/test_derived_provenance.py`, `test_classification.py`,
  `test_quality_duplicate.py`, `test_assembly_trivial.py`, and the headline `test_durable_fk.py`).
  `provenance.py` is the **multi-input DAG** — `DerivedArtifactProvenance.build(...)` computes a
  content-addressed `artifact_id = compute_artifact_id(artifact_type, sorted(inputs), producer_name,
  producer_version, config_hash)` with `generated_at` **excluded**; edges are `ArtifactInput(input_type,
  input_id)` and durable references anchor to `source_record_id` (never `source_identity_key`).
  Producers, each anchoring provenance to `source_record_id`: `classification.classify_source_record`
  (near-deterministic, keyed on the `act_id` namespace prefix — `FR_*`→federal_register/promulgation,
  everything else per `_PREFIX_MAP`, unknown abstains; `fr_default_off` is the retrieval-policy hook),
  `quality.detect_duplicate_rows` (**`duplicate_row` only** — contamination detector deferred;
  cross-record, flags byte-identical `raw_text_hash` within a caller-chosen scope, never deletes),
  and `assembly.assemble_trivial_single_record` (`trivial_single_record_v1`: one member, `KEEP`,
  `complete`, `assembled_text = raw_text` verbatim — **`legal_id` attaches to the assembly, not the
  row**). Closed vocabularies are `enum.StrEnum` (3.12). `SourceIdentityAnnotation`
  (`identity.py`) is the shape only — it **groups/characterizes, never composes**; concrete strategies
  (`usc_act_id_v1`/`cfr_identity_v1`/…) and the CFR multi-row composer (`cfr_source_assembly_v1`) land
  in the CFR path, not here. Duck-typed on `.source_record_id`/`.column('act_id')`, so `derived/` has
  **no runtime import** of the immutable core.
- `src/open_us_law_coverage/hierarchy.py` → `reports/M0.5B2_hierarchy.md` + `tests/test_hierarchy.py`
  (M0.5B2). Both a tested parser and a report harness. `parse_breadcrumb(breadcrumb_json)` is the pure
  core — it turns the `breadcrumb` JSON array (`{type,num,label,name}`, root→leaf) into a normalized
  `HierarchyNode(kind, identifier, label, source, confidence, ordinal, raw_kind, name)` path; **flat
  `title/chapter/section` columns are not read** (M0: unreliable — CA ~70% null title, TX 100%),
  `breadcrumb`/`display_path` are (100% populated). `kind` normalizes via `HierarchyKind` (StrEnum;
  unknown→`other` at reduced confidence, raw preserved); an unnumbered container (`num == ""`, the DE
  `group`s) yields `identifier=None` at half confidence — an **abstention, never a fabricated id**.
  `analyze_corpus` streams the small columns only (`iter_batches(columns=...)`, never `text`), assembles
  an absolute-path-keyed tree, and measures **topology, not just coverage**: acyclicity, proper-tree
  assembly, display-path round-trip (exact vs `label`-is-prefix — `display_path` appends node `name`),
  bare-`(kind,identifier)` leaf ambiguity (why LOCAL resolution needs the absolute path), and
  sibling-order consistency (physical row order vs `natural_key` sort — the budget for RELATIVE-ref
  abstention). Report is byte-stable (deterministic first-seen ordering, sorted output). `EXIT_SECTION`
  holds the qualitative verdict (embedded so it never drifts from the tables). Regenerate:
  `uv run python -m open_us_law_coverage.hierarchy data/v2026.08_full/us_{ca,tx}_statutes.parquet
  data/v2026.08_full/us_{oh,de}_regulations.parquet --snapshot v2026.08 --out reports/M0.5B2_hierarchy.md`.

### Load-bearing design invariants (span the whole system — do not violate)

These come from `PROPOSAL.md` and are the reason the project exists; code that breaks them defeats
the point:

- **Uncertainty about legal identity is represented as data, never hidden in ID-generation code.**
  The system must be able to distinguish "same provision," "probably renumbered into," and "cannot
  establish continuity" as materially different claims.
- **Tiered, evidence-based identity.** `act_id` (verbatim from the dataset, e.g. `USC_T42_C21_S1983`)
  is the Tier-1 identity seed — it is a *normalized citation*, so it is stable under text amendment
  but breaks by construction on renumber/transfer/recodify (those route to Tier-3 lineage
  inference). **Never** compute `legal_id = hash(canonical_citation)`; citation is a resolvable
  alias, not identity. Enforce `act_id` uniqueness on `(state, corpus, act_id)` — `jurisdiction` is
  uniformly `"US"`; `state` is the real discriminator. (M0 finding: `act_id` is 100% populated
  everywhere but **not unique within the federal regulations file** — a Tier-1 caveat.)
- **Deterministic-first, and abstain rather than guess.** An explicit `unresolved`/`ambiguous`
  result beats a confidently wrong edge; `external` (correctly out-of-corpus) is a *success*, kept
  distinct in metrics. A rule-derived edge and an LLM-derived edge must never be indistinguishable in
  storage.
- **Status is snapshot-qualified**: say "in force as represented in Open US Law v2026.08," never
  "currently in force."

### Dataset facts established by M0 (design against these, not the dataset card)

- All 229 files share **one identical 24-column schema** — a single normalizer handles every corpus.
- **No predecessor/successor crosswalk column exists anywhere** → lineage must be inferred. But the
  disposition often sits in the `text` (e.g. `[§2010. Renumbered §321]`), giving a deterministic
  lineage edge for many `renumbered` rows.
- **Flat hierarchy columns (`title_number`/`chapter`/`section_number`) are NOT reliable across
  jurisdictions** (California leaves `title_number` null on ~70% of rows). The structural hierarchy
  lives in `breadcrumb`/`display_path`; read those, not the flat columns.

### Non-obvious constraint: the `text` column can OOM the machine

`us_federal_regulations.parquet` has a `text` column that is ~11 GB uncompressed, with a **single
Parquet row-group reaching ~3.3 GB**. Polars (in-memory *and* the streaming engine, as of 1.44) and
pyarrow `iter_batches` all materialize whole row-groups, so a naive `read_parquet`/`collect` over the
full snapshot OOM-kills a 14 GB box. `recon.py` deliberately splits work: the 23 small columns go
through polars in-memory, and **`text` is scanned row-group-at-a-time via pyarrow with
`pool.release_unused()` between groups** (peak ≈ one row-group), pulling Python strings only for the
handful of lineage-status rows. **Preserve this pattern** — any new full-snapshot pass over `text`
must stay row-group-bounded, or it will crash on the regulations file. Validate changes by rerunning
the 4-file sample and diffing against the committed `reports/M0_recon.md` (must be byte-identical).

**Corollary for aggregation over `text`:** the row-group-bounded pyarrow pattern is for *per-row
Python inspection* (recon's lineage scan). For *aggregates* over `text` (e.g. `COUNT(DISTINCT
md5(text))` per `act_id` in `identity_collisions.py`), pyarrow `read_row_group` still materializes a
whole 3.3 GB row-group and OOMs — **do not** reach for it. Use **DuckDB** with `SET memory_limit` +
`SET temp_directory` instead; it streams the column and spills the aggregate to disk. This is why
`duckdb` is a dependency. Empirically the polars streaming engine, pyarrow `iter_batches`, and the
pyarrow `dataset` scanner *with a filter* **all** still materialize the whole row-group and OOM — only
the DuckDB spill path (or recon's per-row-group release pattern) is safe on this file.
