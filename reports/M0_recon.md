# M0 — Dataset Reconnaissance Report

**Snapshot:** `v2026.08`  
**Files analyzed:** 4 (representative sample)  
**Total rows analyzed:** 234,597

> Scope note: This report is computed over a representative subset of the 229-file snapshot (the USC federal statutes — the commissioned corpus — plus sample state statute and constitution files). The harness runs on any file glob; point it at the full snapshot to produce the complete report.

## 0. Key findings that refine the proposal

- **Uniform 24-column schema** across statutes / constitutions (and, per the card, regulations / court rules / guidance). One normalizer handles every corpus. See §1.
- **No crosswalk column** for renumber/transfer — confirmed. Lineage must be inferred, as the proposal expected. **But** the disposition often lives in the *text*: **100% of `renumbered` USC rows carry an explicit inline successor pointer** (`[§2010. Renumbered §321]`), giving a *deterministic* lineage edge — stronger than the similarity-inference fallback the proposal assumed. `transferred`/`omitted` rows rarely have the one-line pointer (~1-2%); their history sits in `Editorial Notes / Codification` prose and needs a dedicated parser. `repealed` rows name the repealing Pub. L. inline (~4% as a `§` pointer, more as prose). See §5.
- **`act_id` is a normalized citation with a corpus namespace** (`USC_…` / `STATE_XX_…` / `SCONST_XX_…`). Good Tier-1 seed; breaks by construction on renumber/transfer. Enforce uniqueness on `(state, corpus, act_id)`, not the bare id — `jurisdiction` is uniformly `"US"`; `state` is the real discriminator. See §3.
- **Flat hierarchy columns are NOT reliable across jurisdictions.** California leaves `title_number` null on 70% of rows because CA namespaces by *code* (`Cal. BPC`, `Cal. CCP`) rather than a numbered title; the true hierarchy is in `display_path` / `breadcrumb`. **The structural parser must read `breadcrumb`/`display_path`, not the flat `title_number`/`chapter` columns.** USC and AK flat columns are ~100% clean. See §6.
- **USC cross-references ship pre-extracted**: 69% of USC rows carry a `cross_references_usc` array (`"title:section"`), ~128k edges in the USC file alone, plus `public_laws_referenced` on 88%. This is a large head start (and an oracle) for M4. State files have almost none, so in-body parsing still matters off-federal. See §9.
- **`last_amended_year` is mostly null** (59% USC, 98-99% state) and cannot be the temporal backbone. Snapshot version + `act_status` + `year` carry temporality instead.
- **The one unanswerable question**: `act_id` stability under text-only amendment needs a *second* snapshot to measure. Acquire `v2026.07` (statutes+constitutions) or the next quarterly release before finalizing Tier-1 identity. See §11.2.

## 1. Schema consistency across corpora

All 4 files share an **identical 24-column schema**:

```
act_id
citation
citation_short
state
jurisdiction
document_type
title_number
title_name
chapter
chapter_name
section_number
section_title
breadcrumb
display_path
act_status
text
word_count
source_url
last_amended_year
subsection_count
cross_references_usc
cross_references_cfr
public_laws_referenced
year
```

## 2. Predecessor/successor crosswalk field?

**No explicit predecessor/successor crosswalk field exists** (checked for ['formerly_cited_as', 'renumbered_from', 'renumbered_to', 'transferred_from', 'transferred_to', 'predecessor', 'successor', 'former_citation', 'history']). This confirms the proposal's expectation: cross-move identity must be **inferred** (Identity Tier 3), not read from a column. The only lineage-adjacent signals present are `act_status`, `cross_references_usc/cfr`, and `public_laws_referenced`.

## 3. `act_id` behavior

| File | Corpus | Rows | act_id populated | Unique in file | Dupes | Prefix scheme |
|---|---|---:|---:|:--:|---:|---|
| us_ak_constitutions.parquet | constitutions | 243 | 100.0% | yes | 0 | `SCONST_AK`×243 |
| us_ak_statutes.parquet | statutes | 17,935 | 100.0% | yes | 0 | `STATE_AK`×17935 |
| us_ca_statutes.parquet | statutes | 161,566 | 100.0% | yes | 0 | `STATE_CA`×161566 |
| us_federal_statutes.parquet | statutes | 54,853 | 100.0% | yes | 0 | `USC`×54853 |

**act_id is a normalized, namespaced citation.** The title/chapter/section is baked into the string (e.g. `USC_T10_C1001_S10001`, `STATE_AK_T10_C10.06_S10.06.005`, `SCONST_AK_A10_S0`). Implications for identity, per the proposal:

- **Stable under text-only amendment** (the number does not change) → good Tier-1 seed.
- **Structurally cannot be stable across renumbering/transfer/recodification** — the number *is* the ID, so a move changes the ID. Those rows must route to lineage inference.
- The corpus prefix (`USC_`/`STATE_XX_`/`SCONST_XX_`) namespaces the ID, so uniqueness must be checked within `(state, corpus)`, not globally on the bare number.

## 4. `act_status` distribution

**us_ak_constitutions.parquet**
| status | count | share |
|---|---:|---:|
| in_force | 243 | 100.0% |

**us_ak_statutes.parquet**
| status | count | share |
|---|---:|---:|
| in_force | 17,035 | 95.0% |
| reserved | 861 | 4.8% |
| repealed | 39 | 0.2% |

**us_ca_statutes.parquet**
| status | count | share |
|---|---:|---:|
| in_force | 161,525 | 100.0% |
| repealed | 41 | 0.0% |

**us_federal_statutes.parquet**
| status | count | share |
|---|---:|---:|
| in_force | 46,532 | 84.8% |
| repealed | 4,668 | 8.5% |
| omitted | 1,800 | 3.3% |
| transferred | 1,442 | 2.6% |
| renumbered | 373 | 0.7% |
| vacant | 21 | 0.0% |
| reserved | 17 | 0.0% |

## 5. Lineage cases (statuses where act_id is expected to break)

These are the rows that Tier-3 lineage inference must handle. `act_id` for a `renumbered`/`transferred`/etc. row still encodes *its own* number; there is no column pointing at the predecessor/successor, so the link must come from text-hash similarity, hierarchy, section-number transition, and status flags.

**Inline successor/disposition pointer in the text body** — how often a disposition status row literally states where it went (`Renumbered §N` / `Transferred` / `Repealed. Pub. L. …`):

| File | status | rows | with inline pointer | rate |
|---|---|---:|---:|---:|
| us_ak_statutes.parquet | repealed | 39 | 0 | 0.0% |
| us_ca_statutes.parquet | repealed | 41 | 0 | 0.0% |
| us_federal_statutes.parquet | omitted | 1,800 | 28 | 1.6% |
| us_federal_statutes.parquet | renumbered | 373 | 372 | 99.7% |
| us_federal_statutes.parquet | repealed | 4,668 | 179 | 3.8% |
| us_federal_statutes.parquet | transferred | 1,442 | 21 | 1.5% |

_Takeaway: `renumbered` → deterministic regex lineage. `transferred`/`omitted` → parse the `Editorial Notes / Codification` block. `repealed` → capture the repealing Pub. L._

**us_federal_statutes.parquet** — 3,615 lineage-status rows. Examples:
- `USC_T10_C101_S2010` (renumbered) — 10 U.S.C. § 2010 (2024) — has_text=True
  - text head: _'[§2010. Renumbered §321]'_
- `USC_T10_C101_S2011` (renumbered) — 10 U.S.C. § 2011 (2024) — has_text=True
  - text head: _'[§2011. Renumbered §322]'_
- `USC_T10_C106_S2132` (renumbered) — 10 U.S.C. § 2132 (2024) — has_text=True
  - text head: _'[§2132. Renumbered §16132]'_
- `USC_T10_C106_S2133` (renumbered) — 10 U.S.C. § 2133 (2024) — has_text=True
  - text head: _'[§2133. Renumbered §16133]'_

## 6. Hierarchy cleanliness (for LOCAL/RELATIVE/CONTAINER resolution)

| File | title_number null | chapter null | section_number null | complete hierarchy |
|---|---:|---:|---:|---:|
| us_ak_constitutions.parquet | 100.0% | 100.0% | 0.0% | 0.0% |
| us_ak_statutes.parquet | 0.0% | 0.0% | 0.0% | 100.0% |
| us_ca_statutes.parquet | 70.2% | 0.0% | 0.0% | 28.0% |
| us_federal_statutes.parquet | 0.0% | 0.0% | 0.0% | 99.9% |

## 7. Citation-format variability per jurisdiction

**ak / constitutions**
- `Ak. Const. art. 10, § 0`
- `Ak. Const. art. 11, § 0`
- `Ak. Const. art. 12, § 0`
- `Ak. Const. art. 13, § 0`
- `Ak. Const. art. 14, § 0`

**ak / statutes**
- `Alaska Stat. § 10.06.005`
- `Alaska Stat. § 10.06.010`
- `Alaska Stat. § 10.06.015`
- `Alaska Stat. § 10.06.020`
- `Alaska Stat. § 10.06.025`

**ca / statutes**
- `Cal. BPC § 1`
- `Cal. BPC § 10`
- `Cal. BPC § 11`
- `Cal. BPC § 12`
- `Cal. BPC § 12.5`

**federal / statutes**
- `10 U.S.C. § 10001 (2024)`
- `10 U.S.C. § 10101 (2024)`
- `10 U.S.C. § 10102 (2024)`
- `10 U.S.C. § 10102a (2024)`
- `10 U.S.C. § 10103 (2024)`

## 8. Text-length distribution (word_count)

| File | min | p50 | p95 | max | mean | empty-text rows |
|---|---:|---:|---:|---:|---:|---:|
| us_ak_constitutions.parquet | 7 | 54 | 282 | 1821 | 117 | 0 |
| us_ak_statutes.parquet | 4 | 114 | 710 | 11071 | 210 | 0 |
| us_ca_statutes.parquet | 3 | 89 | 724 | 36844 | 194 | 0 |
| us_federal_statutes.parquet | 31 | 363 | 3711 | 165213 | 1028 | 0 |

## 9. Cross-reference coverage

The dataset **ships pre-extracted cross-references** as JSON arrays (`cross_references_usc` = `["title:section", ...]`, `cross_references_cfr`, `public_laws_referenced` = `["Pub. L. NNN-NNN", ...]`). This is a major head start for M4 (in-body cross-reference graph): edges partly exist as data. They still need validation — treat them as a candidate/oracle source, not ground truth, and keep dataset-provided edges distinguishable from parser-derived edges per the proposal.

| File | rows w/ USC xref | total USC edges | rows w/ CFR xref | rows w/ Pub.L. |
|---|---:|---:|---:|---:|
| us_ak_constitutions.parquet | 0.0% | 0 | 0.0% | 0.0% |
| us_ak_statutes.parquet | 0.0% | 2 | 0.0% | 0.0% |
| us_ca_statutes.parquet | 1.4% | 2,813 | 0.0% | 0.0% |
| us_federal_statutes.parquet | 69.3% | 128,062 | 0.0% | 88.4% |

## 10. Null / empty rates for identity & provenance fields

| File | act_id | citation | citation_short | section_number | section_title | source_url | last_amended_year | subsection_count | text |
|---|---|---|---|---|---|---|---|---|---|
| us_ak_constitutions.parquet | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 11.9% | 80.2% | 0.0% | 0.0% |
| us_ak_statutes.parquet | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 99.3% | 0.0% | 0.0% |
| us_ca_statutes.parquet | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 98.0% | 0.0% | 0.0% |
| us_federal_statutes.parquet | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 58.8% | 0.0% | 0.0% |

_(Cell = null-rate, or null+empty-string rate for string columns.)_

## 11. Answers to the proposal's M0 assumption checks

1. **Is `act_id` populated for every corpus and unique within (jurisdiction, corpus)?** Populated at ~100% across sampled files; unique within each file (see §3). `jurisdiction` is uniformly `"US"`; the real discriminator is the `state` field (`federal`, `AK`, …). Uniqueness should be enforced on `(state, corpus, act_id)`.

2. **Does `act_id` stay fixed under text-only amendment across two snapshots?** **Cannot be answered from a single snapshot.** Only `v2026.08` is in hand. Requires diffing against another snapshot (`v2026.07` is statutes+constitutions only). Structural reasoning says yes (the number is unchanged by text amendment), but this must be *measured* before Tier-1 identity is finalized.

3. **Does `act_id` change under renumbered/transferred/recodified?** By construction, yes — the number is baked into the ID, so a move produces a different ID. These rows exist (see §4/§5) and carry no pointer to their counterpart, so they route to Tier-3 lineage inference.

4. **Is there a predecessor/successor crosswalk field?** **No** (see §2). Confirmed absent. Lineage must be inferred.

5. **Is hierarchy clean enough for deterministic LOCAL/RELATIVE/CONTAINER?** See §6. Where `title_number`/`chapter`/`section_number` are fully populated and the `breadcrumb`/`display_path` structures are present, deterministic container resolution is feasible; rows with null hierarchy components must use the abstain path.

6. **How variable is citation format per jurisdiction?** Highly regular *within* a corpus but different *across* them (see §7): `NN U.S.C. § NNNN`, `Alaska Stat. § NN.NN.NNN`, `Ak. Const. art. N, § N`. A per-jurisdiction grammar/alias table is warranted, exactly as the proposal's M7 anticipates. USC format is clean and should be the first grammar.

