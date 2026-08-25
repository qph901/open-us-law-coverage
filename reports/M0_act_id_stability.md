# M0 — `act_id` stability across snapshots (multi-corpus)

**Old:** `v2026.07` → **New:** `v2026.08`

## Cross-corpus summary

| File | rows | unchanged | amended | added | removed | act_id stable? |
|---|---:|---:|---:|---:|---:|:--:|
| us_federal_statutes.parquet | 54,853 | 28,427 | 26,426 | 0 | 0 | yes |
| us_ca_statutes.parquet | 161,566 | 152,547 | 8,882 | 137 | 0 | yes |
| us_ak_statutes.parquet | 17,935 | 16,998 | 937 | 0 | 0 | yes |

_`removed = 0` across every corpus ⇒ no act_id ever disappeared or was reissued between snapshots; `added` is genuinely new sections; `amended` is byte-level text change (federal is inflated by editorial-note growth — see per-file detail)._


---

# M0 — `act_id` stability across snapshots

**File:** `us_federal_statutes.parquet`  
**Old:** `v2026.07` (54,853 rows)  
**New:** `v2026.08` (54,853 rows)

## Verdict

**`act_id` survives text-only amendment.** 26,426 act_ids appear in *both* snapshots with **different text** — the identifier held constant while the provision's text changed. This confirms the proposal's Tier-1 assumption: `act_id` is a safe stable-source identity seed under ordinary amendment.

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
- `USC_T36_C305_S30511`
- `USC_T12_C35_S3406`
- `USC_T45_C17_S821`
- `USC_T42_C7_S1395lll`
- `USC_T38_C20_S2052`
- `USC_T2_C65_S6631`
- `USC_T7_C35A_S1444`
- `USC_T42_C35_S3015`

## Move rows (renumber / transfer / recodify) in the new snapshot

Of 1,815 disposition-status rows checked, 393 state a successor number inline in the text, and 1,815 have an act_id that already existed in `v2026.07`. A move keeps *its own* (old) number as the row's act_id while pointing at the successor — so the successor provision carries a **different** act_id, exactly why cross-move identity cannot ride on act_id and must be linked via `lineage_id`.

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

**`act_id` survives text-only amendment.** 8,882 act_ids appear in *both* snapshots with **different text** — the identifier held constant while the provision's text changed. This confirms the proposal's Tier-1 assumption: `act_id` is a safe stable-source identity seed under ordinary amendment.

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
- `STATE_CA_Cbpc_D9_C15_S25503.57`
- `STATE_CA_Cedc_T3_D10_P59_C8_A11_S94911`
- `STATE_CA_Cwic_D2_P1_C2_A16_S656.2`
- `STATE_CA_Cwic_D9_P3_C7_A7_S14199.71`
- `STATE_CA_Cbpc_D7_P3_C1_A1.4_S17511.5`
- `STATE_CA_Clab_D2_P1_C1_A1_S230.8`
- `STATE_CA_Clab_D1_C4_S96.8`
- `STATE_CA_Chsc_D31_P2_C2.8_S50490.4`

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

Of 0 disposition-status rows checked, 0 state a successor number inline in the text, and 0 have an act_id that already existed in `v2026.07`. A move keeps *its own* (old) number as the row's act_id while pointing at the successor — so the successor provision carries a **different** act_id, exactly why cross-move identity cannot ride on act_id and must be linked via `lineage_id`.



---

# M0 — `act_id` stability across snapshots

**File:** `us_ak_statutes.parquet`  
**Old:** `v2026.07` (17,935 rows)  
**New:** `v2026.08` (17,935 rows)

## Verdict

**`act_id` survives text-only amendment.** 937 act_ids appear in *both* snapshots with **different text** — the identifier held constant while the provision's text changed. This confirms the proposal's Tier-1 assumption: `act_id` is a safe stable-source identity seed under ordinary amendment.

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
- `STATE_AK_T21_C21.22_S21.22.200`
- `STATE_AK_T45_C45.48_S45.48.130`
- `STATE_AK_T13_C13.60_S13.60.170`
- `STATE_AK_T18_C18.57_S18.57.050`
- `STATE_AK_T46_C46.03_S46.03.500`
- `STATE_AK_T23_C23.20_S23.20.350`
- `STATE_AK_T28_C28.35_S28.35.031`
- `STATE_AK_T10_C10.06_S10.06.490`

## Move rows (renumber / transfer / recodify) in the new snapshot

Of 0 disposition-status rows checked, 0 state a successor number inline in the text, and 0 have an act_id that already existed in `v2026.07`. A move keeps *its own* (old) number as the row's act_id while pointing at the successor — so the successor provision carries a **different** act_id, exactly why cross-move identity cannot ride on act_id and must be linked via `lineage_id`.



---
