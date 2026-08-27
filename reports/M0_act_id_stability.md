# M0 — `act_id` stability across snapshots (multi-corpus)

**Old:** `v2026.07` → **New:** `v2026.08`

## Cross-corpus summary

| File | rows | unchanged | amended | added | removed | act_id stable? |
|---|---:|---:|---:|---:|---:|:--:|
| us_federal_statutes.parquet | 54,853 | 28,427 | 26,426 | 0 | 0 | yes |
| us_ca_statutes.parquet | 161,566 | 152,547 | 8,882 | 137 | 0 | yes |
| us_ak_statutes.parquet | 17,935 | 16,998 | 937 | 0 | 0 | yes |

_`removed = 0` across every corpus ⇒ every `act_id` present in the old snapshot is still present in the new one (none dropped); `added` are `act_id`s new to the new snapshot **by set membership**; `amended` counts byte-level `text` change (federal is inflated by editorial-note growth — see per-file detail). Set membership alone does **not** establish that an id was never reissued to a different provision, nor that an `added` id is a brand-new enactment rather than the target of a renumber._


---

# M0 — `act_id` stability across snapshots

**File:** `us_federal_statutes.parquet`  
**Old:** `v2026.07` (54,853 rows)  
**New:** `v2026.08` (54,853 rows)

## Verdict

**Supporting evidence that `act_id` is stable under text change.** 26,426 act_ids appear in *both* snapshots with **different text** — the identifier held constant while the stored `text` changed. This is *consistent with* the proposal's Tier-1 assumption that `act_id` is a stable-source identity seed, but it does **not** by itself confirm it: same-id/different-text cannot, on its own, distinguish a genuine legal amendment from editorial-notes expansion (see the caveat below — a large share is exactly that) or from an `act_id` being reused for a different provision. Treat it as one supporting signal, corroborated by the operative-body split below, not as proof.

## Classification of act_ids

| class | count | share of union |
|---|---:|---:|
| in both, text unchanged | 28,427 | 51.8% |
| in both, text AMENDED | 26,426 | 48.2% |
| added in v2026.08 | 0 | 0.0% |
| removed since v2026.07 | 0 | 0.0% |

## What the text changes actually are (caveat for `text_hash`)

The 26,426 'amended' rows are **not** all real legal amendments. Of them, **26,426 grew and 0 shrank** — the change is essentially **append-only**, and the amended text grew **+24.3%** in total characters. At least **5,381 (20%)** have an **identical operative body** once the OLRC `Editorial Notes / Statutory Notes` apparatus is stripped — i.e. only the historical/editorial notes were expanded between snapshots, not the law.

> **Design implication (M1):** the `text` field bundles operative statutory text with a volatile editorial-notes apparatus. Hashing the whole field makes ~half the corpus look 'amended' between snapshots and would poison both change-detection and text-similarity lineage. **Hash (and diff) the operative body separately from the notes.** `text_hash` over raw `text` is a provenance/integrity hash, not a legal-change signal.

**Stable-but-amended act_id examples (identity held, text changed):**
- `USC_T10_C1001_S10001`
- `USC_T10_C1003_S10101`
- `USC_T10_C1003_S10105`
- `USC_T10_C1005_S10145`
- `USC_T10_C1005_S10147`
- `USC_T10_C1005_S10148`
- `USC_T10_C1005_S10149`
- `USC_T10_C1005_S10154`

## Move rows (renumber / transfer / recodify) in the new snapshot

Of 1,815 disposition-status rows checked, 393 state a successor number inline in the text, and 1,815 have an act_id that already existed in `v2026.07`. The move row keeps *its own* (old) number as the row's act_id while its text points at a successor number. **The stated successor is extracted from the text but not resolved to an actual old/new record here**, so this pass does not by itself prove the successor carries a different act_id — it establishes only that the move row retains its own identifier. That retention is already enough motivation to link cross-move identity via `lineage_id` rather than assume act_id follows the provision; resolving the successor pointer to a record is future lineage work.

| act_id | status | self in old? | successor stated |
|---|---|:--:|---|
| `USC_T10_C101_S2010` | renumbered | yes | 321 |
| `USC_T10_C101_S2011` | renumbered | yes | 322 |
| `USC_T10_C106_S2132` | renumbered | yes | 16132 |
| `USC_T10_C106_S2133` | renumbered | yes | 16133 |
| `USC_T10_C106_S2134` | renumbered | yes | 16134 |
| `USC_T10_C106_S2135` | renumbered | yes | 16135 |
| `USC_T10_C106_S2136` | renumbered | yes | 16136 |
| `USC_T10_C106_S2137` | renumbered | yes | 16137 |



---

# M0 — `act_id` stability across snapshots

**File:** `us_ca_statutes.parquet`  
**Old:** `v2026.07` (161,429 rows)  
**New:** `v2026.08` (161,566 rows)

## Verdict

**Supporting evidence that `act_id` is stable under text change.** 8,882 act_ids appear in *both* snapshots with **different text** — the identifier held constant while the stored `text` changed. This is *consistent with* the proposal's Tier-1 assumption that `act_id` is a stable-source identity seed, but it does **not** by itself confirm it: same-id/different-text cannot, on its own, distinguish a genuine legal amendment from editorial-notes expansion (see the caveat below — a large share is exactly that) or from an `act_id` being reused for a different provision. Treat it as one supporting signal, corroborated by the operative-body split below, not as proof.

## Classification of act_ids

| class | count | share of union |
|---|---:|---:|
| in both, text unchanged | 152,547 | 94.4% |
| in both, text AMENDED | 8,882 | 5.5% |
| added in v2026.08 | 137 | 0.1% |
| removed since v2026.07 | 0 | 0.0% |

## What the text changes actually are (caveat for `text_hash`)

The 8,882 'amended' rows are **not** all real legal amendments. Of them, **8,819 grew and 57 shrank** — the change is essentially **append-only**, and the amended text grew **+9.4%** in total characters. At least **0 (0%)** have an **identical operative body** once the OLRC `Editorial Notes / Statutory Notes` apparatus is stripped — i.e. only the historical/editorial notes were expanded between snapshots, not the law.

> **Design implication (M1):** the `text` field bundles operative statutory text with a volatile editorial-notes apparatus. Hashing the whole field makes ~half the corpus look 'amended' between snapshots and would poison both change-detection and text-similarity lineage. **Hash (and diff) the operative body separately from the notes.** `text_hash` over raw `text` is a provenance/integrity hash, not a legal-change signal.

**Stable-but-amended act_id examples (identity held, text changed):**
- `STATE_CA_Cbpc_AGENERAL PROVISIONS_S27`
- `STATE_CA_Cbpc_AGENERAL PROVISIONS_S27.5`
- `STATE_CA_Cbpc_AGENERAL PROVISIONS_S30`
- `STATE_CA_Cbpc_D1.5_C2_S480`
- `STATE_CA_Cbpc_D1.5_C2_S480.2`
- `STATE_CA_Cbpc_D1.5_C3_S494`
- `STATE_CA_Cbpc_D1.5_C3_S494.5`
- `STATE_CA_Cbpc_D10_C10_S26100`

**Added-in-v2026.08 examples:**
- `STATE_CA_Cedc_T1_D1_P10.5_C3_A7_S17376`
- `STATE_CA_Cedc_T1_D1_P10_C12.5_A9_S17076.12`
- `STATE_CA_Cedc_T1_D1_P1_C2_A2.5_S216.5`
- `STATE_CA_Cedc_T1_D1_P2_C12.5_S2575.35`
- `STATE_CA_Cedc_T1_D1_P2_C12.5_S2580`
- `STATE_CA_Cedc_T1_D1_P2_C12.5_S2581`
- `STATE_CA_Cedc_T1_D1_P2_C12.5_S2582`
- `STATE_CA_Cedc_T1_D1_P2_C12.5_S2583`

## Move rows (renumber / transfer / recodify) in the new snapshot

Of 0 disposition-status rows checked, 0 state a successor number inline in the text, and 0 have an act_id that already existed in `v2026.07`. The move row keeps *its own* (old) number as the row's act_id while its text points at a successor number. **The stated successor is extracted from the text but not resolved to an actual old/new record here**, so this pass does not by itself prove the successor carries a different act_id — it establishes only that the move row retains its own identifier. That retention is already enough motivation to link cross-move identity via `lineage_id` rather than assume act_id follows the provision; resolving the successor pointer to a record is future lineage work.



---

# M0 — `act_id` stability across snapshots

**File:** `us_ak_statutes.parquet`  
**Old:** `v2026.07` (17,935 rows)  
**New:** `v2026.08` (17,935 rows)

## Verdict

**Supporting evidence that `act_id` is stable under text change.** 937 act_ids appear in *both* snapshots with **different text** — the identifier held constant while the stored `text` changed. This is *consistent with* the proposal's Tier-1 assumption that `act_id` is a stable-source identity seed, but it does **not** by itself confirm it: same-id/different-text cannot, on its own, distinguish a genuine legal amendment from editorial-notes expansion (see the caveat below — a large share is exactly that) or from an `act_id` being reused for a different provision. Treat it as one supporting signal, corroborated by the operative-body split below, not as proof.

## Classification of act_ids

| class | count | share of union |
|---|---:|---:|
| in both, text unchanged | 16,998 | 94.8% |
| in both, text AMENDED | 937 | 5.2% |
| added in v2026.08 | 0 | 0.0% |
| removed since v2026.07 | 0 | 0.0% |

## What the text changes actually are (caveat for `text_hash`)

The 937 'amended' rows are **not** all real legal amendments. Of them, **933 grew and 4 shrank** — the change is essentially **append-only**, and the amended text grew **+8.8%** in total characters. At least **0 (0%)** have an **identical operative body** once the OLRC `Editorial Notes / Statutory Notes` apparatus is stripped — i.e. only the historical/editorial notes were expanded between snapshots, not the law.

> **Design implication (M1):** the `text` field bundles operative statutory text with a volatile editorial-notes apparatus. Hashing the whole field makes ~half the corpus look 'amended' between snapshots and would poison both change-detection and text-similarity lineage. **Hash (and diff) the operative body separately from the notes.** `text_hash` over raw `text` is a provenance/integrity hash, not a legal-change signal.

**Stable-but-amended act_id examples (identity held, text changed):**
- `STATE_AK_T10_C10.06_S10.06.210`
- `STATE_AK_T10_C10.06_S10.06.411`
- `STATE_AK_T10_C10.06_S10.06.420`
- `STATE_AK_T10_C10.06_S10.06.433`
- `STATE_AK_T10_C10.06_S10.06.435`
- `STATE_AK_T10_C10.06_S10.06.490`
- `STATE_AK_T10_C10.06_S10.06.576`
- `STATE_AK_T10_C10.06_S10.06.578`

## Move rows (renumber / transfer / recodify) in the new snapshot

Of 0 disposition-status rows checked, 0 state a successor number inline in the text, and 0 have an act_id that already existed in `v2026.07`. The move row keeps *its own* (old) number as the row's act_id while its text points at a successor number. **The stated successor is extracted from the text but not resolved to an actual old/new record here**, so this pass does not by itself prove the successor carries a different act_id — it establishes only that the move row retains its own identifier. That retention is already enough motivation to link cross-move identity via `lineage_id` rather than assume act_id follows the provision; resolving the successor pointer to a record is future lineage work.



---
