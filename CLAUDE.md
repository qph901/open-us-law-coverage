# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A **citation detection / parsing / normalization / resolution** subsystem over the gated
`vaquill/open-us-law` dataset (snapshot **v2026.08**), commissioned on the US Code. It is the
deliberate *foundation* of a legal RAG system — the goal is to reliably identify what law a
citation refers to, with an auditable explanation, **before** any embeddings.

**`PROPOSAL.md` is the source of truth for scope, design, and milestones — read it before making
design decisions.** Milestone status lives in `README.md`. As of this writing M0 (dataset
reconnaissance) is complete; the current phase is the **M0.5 commissioning spikes → M1 split**
(M0.5A identity-collision analysis + M1A lossless source serializer first — see PROPOSAL.md
"Milestones" and "First action for Claude Code").

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
`reports/` **are** committed. There is no test suite yet — the proposal calls for golden-fixture
invariant tests starting at M1; don't invent test commands that don't exist.

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
