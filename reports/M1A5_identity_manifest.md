# M1A.5 — full-snapshot identity manifest

Snapshot: **v2026.08**. Files: **229**. Rows: **2,978,617**. Identity groups (distinct `act_id` per file): **2,809,875**. Two passes, kept distinct: **structural `act_id` sizing** over *every* file (a count of dataset structure, not a producer run — no artifact is constructed), and the **concrete Phase-B producers** (`cfr_identity_v1` / `federal_register_document_v1` / `state_regulation_v1` + within-group `detect_duplicate_rows`) run **only over the colliding groups**. A single-member count below is structure, not evidence a 1:1 producer accepted the row.

## Per-corpus group structure

| corpus | files | rows | groups | single-member | multi-member | max size |
|---|--:|--:|--:|--:|--:|--:|
| `administrative_guidance` | 2 | 11 | 11 | 11 (100.00%) | 0 | 1 |
| `constitutions` | 52 | 13,382 | 13,382 | 13,382 (100.00%) | 0 | 1 |
| `court_rules` | 44 | 43,809 | 43,809 | 43,809 (100.00%) | 0 | 1 |
| `enforcement_action` | 1 | 140 | 140 | 140 (100.00%) | 0 | 1 |
| `executive_order` | 1 | 738 | 738 | 738 (100.00%) | 0 | 1 |
| `faq` | 1 | 444 | 444 | 444 (100.00%) | 0 | 1 |
| `guidance` | 50 | 25,461 | 25,461 | 25,461 (100.00%) | 0 | 1 |
| `guideline` | 1 | 302 | 302 | 302 (100.00%) | 0 | 1 |
| `irs_announcement` | 1 | 83 | 83 | 83 (100.00%) | 0 | 1 |
| `irs_notice` | 1 | 759 | 759 | 759 (100.00%) | 0 | 1 |
| `irs_rev_proc` | 1 | 377 | 377 | 377 (100.00%) | 0 | 1 |
| `irs_rev_rul` | 1 | 245 | 245 | 245 (100.00%) | 0 | 1 |
| `memorandum` | 1 | 401 | 401 | 401 (100.00%) | 0 | 1 |
| `presidential_document` | 1 | 655 | 655 | 655 (100.00%) | 0 | 1 |
| `proclamation` | 1 | 1,832 | 1,832 | 1,832 (100.00%) | 0 | 1 |
| `regulations` | 17 | 885,121 | 716,379 | 549,035 (76.64%) | 167,344 | 14 |
| `ruling` | 1 | 7,248 | 7,248 | 7,248 (100.00%) | 0 | 1 |
| `statutes` | 51 | 1,997,490 | 1,997,490 | 1,997,490 (100.00%) | 0 | 1 |
| `treaty` | 1 | 119 | 119 | 119 (100.00%) | 0 | 1 |

- **94.04%** of all groups are single-member (1:1 source→document); multi-member groups: **167,344**.
- collision files (any `act_id` repeats): `us_federal_regulations.parquet`, `us_il_regulations.parquet`, `us_ky_regulations.parquet`, `us_md_regulations.parquet`, `us_me_regulations.parquet`, `us_mn_regulations.parquet`, `us_oh_regulations.parquet`

## Regulations collision deep-dive (real producers)

Aggregated across every collision file: `us_federal_regulations.parquet`, `us_il_regulations.parquet`, `us_ky_regulations.parquet`, `us_md_regulations.parquet`, `us_me_regulations.parquet`, `us_mn_regulations.parquet`, `us_oh_regulations.parquet`. Multi-member groups are the only place identity composes more than one row — and even there it *groups*, never *concatenates*.

| strategy (namespace) | multi-member groups | rows |
|---|--:|--:|
| `cfr_identity_v1` | 1,083 | 2,236 |
| `federal_register_document_v1` | 165,067 | 331,045 |
| `state_regulation_v1` | 1,194 | 2,805 |

- **within-group duplicate rows** (real `detect_duplicate_rows`, per group): **2,626**.
- single-member (1:1) groups within the collision files: **354,354**.
- **max group size**: 14.
- group `identity_status`: `ambiguous`:165,067, `provisional`:2,277, `resolved`:354,354
- outcome split (of groups in collision files): **resolved** (1:1) 67.92%, **provisional** (multi-segment candidate, assembly to confirm) 0.44%, **ambiguous** (FR numbering bucket, never composed) 31.64%. All three are safe non-fabrication outcomes; only `resolved` is a committed 1:1 identity.

### Group-size distribution (collision files)

| group size | groups |
|--:|--:|
| 1 | 354,354 |
| 2 | 166,210 |
| 3 | 1,055 |
| 4 | 33 |
| 5 | 5 |
| 6 | 10 |
| 7 | 12 |
| 8 | 4 |
| 9 | 2 |
| 10 | 5 |
| 11 | 1 |
| 12 | 3 |
| 13 | 3 |
| 14 | 1 |

## What this establishes

- **Identity is structurally 1:1 outside the regulations corpora** — every statute,
  constitution, court-rule, and guidance file is entirely single-member `act_id`
  groups. This is a *structural* measurement (the sizing pass), **not** a claim that a
  concrete producer ran: the built 1:1 producers cover statutes and constitutions
  (`usc_act_id_v1` / `state_statute_act_id_v1` / `constitution_act_id_v1`), while
  court-rules and guidance have **no** concrete strategy yet — their single-member
  counts here are structure awaiting a producer, not producer output.
- **`act_id` collisions are a *regulations* phenomenon, and not federal-only** — a
  finding this manifest surfaced: alongside `us_federal_regulations` (CFR + FR),
  several **state administrative-code** corpora repeat an `act_id` across rows. The
  router splits every collision group by namespace: CFR / state-regulation →
  `provisional` multi-segment candidates (assembly/anatomy confirms, CFR-A2); FR →
  `ambiguous` co-numbered captures that are never composed.
- **`duplicate_row` is scoped to the group.** Within-group duplicate rows are
  counted by the real `detect_duplicate_rows` run inside each group — never across
  groups, so byte-identical text under *different* `act_id`s is not conflated (the
  M0.5B3 content-vs-identity finding, confirmed at snapshot scale).
- **Abstention is a first-class, measured outcome**, not an error, and its kinds are
  reported **separately**: `resolved` (a committed 1:1 identity), `provisional` (a
  multi-segment candidate assembly must confirm), and `ambiguous` (an FR numbering
  bucket, never composed) are three distinct safe outcomes — none collapsed into a
  single "ambiguity rate".

This report is byte-stable and is the regression fixture for the next
regulations-bearing snapshot.
