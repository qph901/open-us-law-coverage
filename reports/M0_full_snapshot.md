# M0 — Full-Snapshot Reconnaissance

**Snapshot:** `v2026.08`  
**Files:** 229  
**Total rows:** 2,978,617

## 1. Schema consistency across all files

**All 229 files share one identical 24-column schema** — a single normalizer handles every corpus and jurisdiction. Columns: `act_id`, `citation`, `citation_short`, `state`, `jurisdiction`, `document_type`, `title_number`, `title_name`, `chapter`, `chapter_name`, `section_number`, `section_title`, `breadcrumb`, `display_path`, `act_status`, `text`, `word_count`, `source_url`, `last_amended_year`, `subsection_count`, `cross_references_usc`, `cross_references_cfr`, `public_laws_referenced`, `year`

## 2. Predecessor/successor crosswalk field?

**No crosswalk column anywhere in the snapshot.** Lineage across renumber/transfer/recodify must be inferred (Identity Tier 3). Confirmed at full-snapshot scale.

## 3. Per-corpus rollup

| Corpus | files | rows | act_id 100%? | median hierarchy-complete | statuses seen |
|---|---:|---:|:--:|---:|---|
| statutes | 51 | 1,997,490 | yes | 98.0% | expired, in_force, inactive, not_funded, omitted, recodified … |
| regulations | 17 | 885,121 | yes | 0.0% | <null>, expired, in_force, repealed, reserved, transferred |
| court_rules | 44 | 43,809 | yes | 0.0% | in_force, renumbered, repealed, reserved, superseded |
| guidance | 50 | 25,461 | yes | 0.0% | expired, in_force, repealed, rescinded, reserved, revoked … |
| constitutions | 52 | 13,382 | yes | 0.0% | in_force, omitted, repealed, reserved, superseded |
| ruling | 1 | 7,248 | yes | 15.4% | in_force, rescinded |
| proclamation | 1 | 1,832 | yes | 0.0% | in_force |
| irs_notice | 1 | 759 | yes | 100.0% | in_force |
| executive_order | 1 | 738 | yes | 0.0% | in_force |
| presidential_document | 1 | 655 | yes | 0.0% | in_force |
| faq | 1 | 444 | yes | 0.0% | in_force |
| memorandum | 1 | 401 | yes | 0.0% | in_force |
| irs_rev_proc | 1 | 377 | yes | 100.0% | in_force |
| guideline | 1 | 302 | yes | 0.0% | in_force |
| irs_rev_rul | 1 | 245 | yes | 100.0% | in_force |
| enforcement_action | 1 | 140 | yes | 0.0% | in_force |
| treaty | 1 | 119 | yes | 0.0% | in_force |
| irs_announcement | 1 | 83 | yes | 100.0% | in_force |
| administrative_guidance | 2 | 11 | yes | 0.0% | in_force |

## 4. `act_id` namespace schemes observed

| prefix | rows |
|---|---:|
| `FR_…` | 362,036 |
| `CFR_…` | 220,018 |
| `STATE_TX_…` | 166,782 |
| `STATE_CA_…` | 161,566 |
| `STATE_MS_…` | 158,688 |
| `STATE_IL_…` | 126,040 |
| `STATE_WA_…` | 102,524 |
| `STATE_IN_…` | 83,148 |
| `STATE_SD_…` | 68,577 |
| `STATE_VA_…` | 56,253 |
| `STATE_NJ_…` | 55,993 |
| `USC_…` | 54,853 |
| `STATE_OH_…` | 53,070 |
| `STATE_MD_…` | 52,415 |
| `STATE_NV_…` | 48,190 |
| `STATE_AL_…` | 45,984 |
| `STATE_LA_…` | 43,512 |
| `STATE_MN_…` | 43,194 |
| `STATE_MI_…` | 40,658 |
| `STATE_NY_…` | 40,140 |
| `STATE_AR_…` | 36,936 |
| `STATE_SC_…` | 36,553 |
| `STATE_OR_…` | 36,202 |
| `STATE_WI_…` | 35,981 |
| `STATE_OK_…` | 35,329 |
| `STATE_CO_…` | 34,841 |
| `STATE_NM_…` | 34,455 |
| `STATE_TN_…` | 32,693 |
| `STATE_ID_…` | 31,305 |
| `STATE_MT_…` | 30,514 |
| `STATE_MO_…` | 29,309 |
| `STATE_ND_…` | 29,042 |
| `STATE_IA_…` | 28,223 |
| `STATE_ME_…` | 27,034 |
| `STATE_NE_…` | 25,997 |
| `STATE_UT_…` | 25,880 |
| `STATE_KY_…` | 25,759 |
| `STATE_WV_…` | 25,664 |
| `STATE_NH_…` | 25,375 |
| `STATE_FL_…` | 24,866 |
| `STATE_KS_…` | 24,361 |
| `STATE_DC_…` | 23,694 |
| `STATE_PR_…` | 23,636 |
| `STATE_VT_…` | 23,521 |
| `STATE_MA_…` | 23,152 |
| `STATE_DE_…` | 22,813 |
| `STATE_AZ_…` | 22,674 |
| `STATE_RI_…` | 21,107 |
| `STATE_WY_…` | 20,999 |
| `STATE_HI_…` | 19,197 |
| `STATE_AK_…` | 17,935 |
| `STATE_CT_…` | 16,082 |
| `STATE_PA_…` | 14,571 |
| `SREGS_NM_…` | 13,270 |
| `DDTC_CJ_…` | 5,879 |
| `EXEC_…` | 3,626 |
| `FDIC_…` | 2,313 |
| `SRULES_ND_…` | 2,246 |
| `TMEP_…` | 2,109 |
| `MPEP_…` | 2,024 |
| `SRULES_CT_…` | 1,723 |
| `SRULES_PA_…` | 1,722 |
| `SRULES_AZ_…` | 1,718 |
| `PR_…` | 1,641 |
| `JM_…` | 1,548 |
| `SRULES_PR_…` | 1,528 |
| `SRULES_CA_…` | 1,521 |
| `SRULES_DE_…` | 1,385 |
| `SRULES_NV_…` | 1,338 |
| `SRULES_IA_…` | 1,294 |
| `SRULES_HI_…` | 1,259 |
| `TX_…` | 1,254 |
| `SRULES_MD_…` | 1,220 |
| `NY_CL_…` | 1,199 |
| `SRULES_WA_…` | 1,182 |
| `SRULES_GA_…` | 1,174 |
| `SRULES_OH_…` | 1,167 |
| `SRULES_DC_…` | 1,128 |
| `SRULES_WV_…` | 1,116 |
| `SSA_…` | 1,115 |
| `SRULES_NY_…` | 1,088 |
| `OCC_…` | 1,054 |
| `SRULES_RI_…` | 1,033 |
| `SRULES_MI_…` | 1,025 |
| `SRULES_WY_…` | 1,010 |
| `SRULES_TX_…` | 1,007 |
| `SRULES_MA_…` | 970 |
| `SRULES_NH_…` | 970 |
| `SRULES_MN_…` | 958 |
| `CFTC_…` | 942 |
| `SRULES_FL_…` | 936 |
| `SRULES_UT_…` | 919 |
| `SRULES_IN_…` | 879 |
| `SRULES_AL_…` | 870 |
| `IRS_…` | 842 |
| `SRULES_IL_…` | 839 |
| `SRULES_MS_…` | 794 |
| `SRULES_ID_…` | 766 |
| `SRULES_AK_…` | 763 |
| `SRULES_NE_…` | 734 |
| `SRULES_ME_…` | 722 |
| `MD_…` | 675 |
| `SCONST_AZ_…` | 646 |
| `NLRB_…` | 639 |
| `SRULES_OR_…` | 632 |
| `SRULES_TN_…` | 626 |
| `HHS_…` | 625 |
| `FRULES_…` | 589 |
| `SRULES_SC_…` | 557 |
| `SCONST_OK_…` | 545 |
| `SCONST_AR_…` | 513 |
| `SRULES_NC_…` | 495 |
| `SRULES_LA_…` | 481 |
| `CA_…` | 463 |
| `USCIS_PM_…` | 456 |
| `SCONST_NE_…` | 448 |
| `SCONST_MO_…` | 445 |
| `NJ_…` | 441 |
| `SRULES_KS_…` | 434 |
| `SCONST_CO_…` | 424 |
| `MA_…` | 417 |
| `SCONST_OR_…` | 415 |
| `SCONST_TX_…` | 401 |
| `AK_…` | 398 |
| `PGI_…` | 397 |
| `SRULES_WI_…` | 395 |
| `SCONST_AL_…` | 381 |
| `IRS_RP_…` | 377 |
| `CT_…` | 369 |
| `SCONST_CA_…` | 362 |
| `AR_…` | 359 |
| `SRULES_VA_…` | 358 |
| `FRB_…` | 336 |
| `SCONST_LA_…` | 328 |
| `SC_…` | 319 |
| `SCONST_MS_…` | 318 |
| `SCONST_WY_…` | 316 |
| `SCONST_MD_…` | 312 |
| `SCONST_MI_…` | 307 |
| `DE_…` | 303 |
| `USSG_…` | 302 |
| `SCONST_NM_…` | 299 |
| `SCONST_SD_…` | 294 |
| `SCONST_GA_…` | 287 |
| `SCONST_WA_…` | 282 |
| `IN_…` | 281 |
| `SCONST_KY_…` | 274 |
| `NM_…` | 274 |
| `SCONST_OH_…` | 266 |
| `IRS_RR_…` | 245 |
| `SCONST_SC_…` | 245 |
| `SCONST_AK_…` | 243 |
| `SCONST_ID_…` | 240 |
| `MS_…` | 240 |
| `SRULES_MT_…` | 238 |
| `ND_…` | 235 |
| `SCONST_NV_…` | 234 |
| `KY_…` | 232 |
| `WI_…` | 232 |
| `SCONST_KS_…` | 229 |
| `ME_…` | 228 |
| `SCONST_DE_…` | 225 |
| `SCONST_FL_…` | 217 |
| `SCONST_NJ_…` | 216 |
| `FINCEN_…` | 212 |
| `SCONST_WV_…` | 209 |
| `AL_…` | 207 |
| `SCONST_NY_…` | 204 |
| `SCONST_ND_…` | 203 |
| `AZ_…` | 199 |
| `NV_…` | 199 |
| `SCONST_IN_…` | 196 |
| `SCONST_MT_…` | 196 |
| `SCONST_IA_…` | 190 |
| `SCONST_UT_…` | 189 |
| `VT_…` | 187 |
| `SCONST_PA_…` | 186 |
| `NH_…` | 177 |
| `SCONST_WI_…` | 175 |
| `SCONST_CT_…` | 174 |
| `WV_…` | 174 |
| `TN_…` | 173 |
| `SCONST_HI_…` | 171 |
| `SCONST_IL_…` | 170 |
| `HI_…` | 168 |
| `UT_…` | 168 |
| `IL_…` | 158 |
| `SCONST_NH_…` | 157 |
| `SCONST_NC_…` | 155 |
| `SCONST_ME_…` | 153 |
| `SCONST_TN_…` | 152 |
| `MT_…` | 149 |
| `MI_…` | 145 |
| `OK_…` | 144 |
| `CPSC_AO_…` | 139 |
| `SCONST_MN_…` | 138 |
| `RI_…` | 134 |
| `SCONST_VA_…` | 134 |
| `NC_…` | 120 |
| `NE_…` | 120 |
| `SCONST_VT_…` | 120 |
| `TREATY_US_…` | 119 |
| `SCONST_RI_…` | 118 |
| `OH_…` | 112 |
| `FCC_DA_…` | 107 |
| `MO_…` | 106 |
| `SCONST_MA_…` | 104 |
| `SCONST_PR_…` | 102 |
| `OR_…` | 92 |
| `VA_…` | 89 |
| `IA_…` | 83 |
| `KS_…` | 79 |
| `ID_…` | 75 |
| `CONST_US_…` | 74 |
| `GA_…` | 66 |
| `FCC_…` | 62 |
| `WY_…` | 62 |
| `GUID_…` | 60 |
| `DOE_…` | 60 |
| `FERC_…` | 45 |
| `FL_…` | 43 |
| `CPSC_…` | 34 |
| `MN_…` | 34 |
| `BIS_AO_…` | 33 |
| `SD_…` | 27 |
| `WA_…` | 24 |
| `DC_…` | 23 |
| `<no-prefix>_…` | 11 |
| `DDTC_…` | 7 |

_The prefix namespaces the id by corpus+jurisdiction, so enforce act_id uniqueness on `(state, corpus, act_id)`._

## 5. Hierarchy-cleanliness outliers (statutes/regulations)

Files where flat `title_number`/`chapter`/`section_number` do **not** give a complete hierarchy on most rows — these must resolve structure from `breadcrumb`/`display_path` instead (the California pattern). Showing files with <90% complete hierarchy:

| File | rows | complete hierarchy | title_number null |
|---|---:|---:|---:|
| us_ak_constitutions.parquet | 243 | 0.0% | 100.0% |
| us_ak_court_rules.parquet | 763 | 0.0% | 100.0% |
| us_ak_guidance.parquet | 398 | 0.0% | 100.0% |
| us_al_constitutions.parquet | 381 | 0.0% | 100.0% |
| us_al_court_rules.parquet | 870 | 0.0% | 100.0% |
| us_al_guidance.parquet | 207 | 0.0% | 100.0% |
| us_ar_constitutions.parquet | 513 | 0.0% | 100.0% |
| us_ar_guidance.parquet | 359 | 0.0% | 100.0% |
| us_az_constitutions.parquet | 646 | 0.0% | 100.0% |
| us_az_court_rules.parquet | 1,718 | 0.0% | 100.0% |
| us_az_guidance.parquet | 199 | 0.0% | 100.0% |
| us_ca_constitutions.parquet | 362 | 0.0% | 100.0% |
| us_ca_court_rules.parquet | 1,521 | 0.0% | 100.0% |
| us_ca_guidance.parquet | 463 | 0.0% | 100.0% |
| us_co_constitutions.parquet | 424 | 0.0% | 100.0% |
| us_co_regulations.parquet | 610 | 0.0% | 100.0% |
| us_co_statutes.parquet | 34,231 | 0.0% | 0.0% |
| us_ct_constitutions.parquet | 174 | 0.0% | 100.0% |
| us_ct_court_rules.parquet | 1,723 | 0.0% | 100.0% |
| us_ct_guidance.parquet | 369 | 0.0% | 100.0% |
| us_dc_court_rules.parquet | 1,128 | 0.0% | 100.0% |
| us_de_constitutions.parquet | 225 | 0.0% | 100.0% |
| us_de_court_rules.parquet | 1,385 | 0.0% | 100.0% |
| us_de_guidance.parquet | 303 | 0.0% | 100.0% |
| us_de_regulations.parquet | 1,164 | 0.0% | 0.0% |
| us_federal_constitutions.parquet | 74 | 0.0% | 100.0% |
| us_federal_court_rules.parquet | 589 | 0.0% | 100.0% |
| us_federal_enforcement_action.parquet | 140 | 0.0% | 0.0% |
| us_federal_executive_order.parquet | 738 | 0.0% | 100.0% |
| us_federal_faq.parquet | 444 | 0.0% | 0.0% |
| us_federal_guidance.parquet | 12,364 | 0.0% | 49.6% |
| us_federal_guideline.parquet | 302 | 0.0% | 0.0% |
| us_federal_memorandum.parquet | 401 | 0.0% | 100.0% |
| us_federal_presidential_document.parquet | 655 | 0.0% | 100.0% |
| us_federal_proclamation.parquet | 1,832 | 0.0% | 100.0% |
| us_federal_treaty.parquet | 119 | 0.0% | 0.0% |
| us_fl_constitutions.parquet | 217 | 0.0% | 100.0% |
| us_fl_court_rules.parquet | 936 | 0.0% | 100.0% |
| us_fl_statutes.parquet | 24,866 | 0.0% | 100.0% |
| us_ga_constitutions.parquet | 287 | 0.0% | 100.0% |

_182 of 229 files fall below 90% flat-hierarchy completeness._

## 6. Citation-format catalog (one exemplar per file)

| jurisdiction | corpus | example citation |
|---|---|---|
| dc | administrative_guidance | `D.C. Code 32-581.01` |
| federal | administrative_guidance | `IRS Notice 2025-67` |
| ak | constitutions | `Ak. Const. art. 10, § 0` |
| al | constitutions | `Ala. Const. art. III, § 42` |
| ar | constitutions | `Ar. Const. art. 10, § 1` |
| az | constitutions | `Ariz. Const. art. 0, § 0` |
| ca | constitutions | `Cal. Const. art. III, § 1` |
| co | constitutions | `Co. Const. art. III, § 0` |
| ct | constitutions | `Conn. Const. Preamble` |
| de | constitutions | `Del. Const. Preamble` |
| federal | constitutions | `U.S. Const. art. I, § 1` |
| fl | constitutions | `Fla. Const. art. III, § 1` |
| ga | constitutions | `Ga. Const. art. I, § III, para. I` |
| hi | constitutions | `Hi. Const. art. III, § 1` |
| ia | constitutions | `Iowa Const. art. III, § 1` |
| id | constitutions | `Id. Const. art. III, § 1` |
| il | constitutions | `Ill. Const. art. 1, § 1` |
| in | constitutions | `In. Const. art. 10, § 1` |
| ks | constitutions | `Ks. Const. art. 0, § 0` |
| ky | constitutions | `Ky. Const. art. I, § 1` |
| la | constitutions | `La. Const. art. III, § 1` |
| ma | constitutions | `Ma. Const. art. 1, § I` |
| md | constitutions | `Md. Const. art. 1, § 0` |
| me | constitutions | `Me. Const. art. III, § 1` |
| mi | constitutions | `Mi. Const. art. III, § 1` |
| mn | constitutions | `Minn. Const. art. 0, § 0` |
| mo | constitutions | `Mo. Const. art. III, § 1` |
| ms | constitutions | `Ms. Const. art. 10, § 223` |
| mt | constitutions | `Mt. Const. art. III, § 1` |
| nc | constitutions | `Nc. Const. art. 0, § 0` |
| nd | constitutions | `N.D. Const. art. III, § 1` |
| ne | constitutions | `Ne. Const. art. 0, § 0` |
| nh | constitutions | `Nh. Const. art. 1, § 0` |
| nj | constitutions | `Nj. Const. art. II.II, § 1` |
| nm | constitutions | `Nm. Const. art. III, § 1` |
| nv | constitutions | `Nv. Const. art. 10, § 2` |
| ny | constitutions | `N.Y. Const. art. 0, § 0` |
| oh | constitutions | `Oh. Const. art. III, § 1` |
| ok | constitutions | `Ok. Const. art. III, § 1` |
| or | constitutions | `Or. Const. art. III, § 1` |
| pa | constitutions | `Pa. Const. art. III, § 1` |
| pr | constitutions | `P.R. Const. art. III, § 1` |
| ri | constitutions | `Ri. Const. art. III, § 1` |
| sc | constitutions | `S.C. Const. art. III, § 1` |
| sd | constitutions | `S.D. Const. Preamble` |
| tn | constitutions | `Tn. Const. art. III, § 1` |
| tx | constitutions | `Tex. Const. art. 10, § 1` |
| ut | constitutions | `Ut. Const. art. III, § 0` |
| va | constitutions | `Va. Const. art. 13, § 1` |
| vt | constitutions | `Vt. Const. art. 10, § 0` |
| wa | constitutions | `Wa. Const. art. III, § 1` |
| wi | constitutions | `Wis. Const. art. III, § 0` |
| wv | constitutions | `Wv. Const. art. III, § 0` |
| wy | constitutions | `Wy. Const. art. 10, § 1` |
| ak | court_rules | `Alaska R. Admin. 1` |
| al | court_rules | `Ala. Canons Jud. Ethics, Canon 1` |
| az | court_rules | `Ariz. R. P. Jud. Rev. Admin. Decisions 1` |
| ca | court_rules | `Cal. R. Ct. 10.1` |
| ct | court_rules | `Conn. Code Evid. Sec. 10-1` |
| dc | court_rules | `D.C. App. R. 1` |
| de | court_rules | `Del. Com. Pl. Ct. Civ. R. 1` |
| federal | court_rules | `Fed. R. App. P. 1` |
| fl | court_rules | `Fla. R. App. P. 3.800` |
| ga | court_rules | `Ga. Code Jud. Conduct R. 1.1` |
| hi | court_rules | `Haw. R. Cert. Spoken-Lang. Interp. 1` |
| ia | court_rules | `Iowa Ct. R. 10.1` |
| id | court_rules | `I.A.R. 1` |
| il | court_rules | `IL. R. Ct. 301` |
| in | court_rules | `Ind. Admis. Disc. R. 1` |
| ks | court_rules | `Kan. S. Ct. R. 240, Preamble: A Lawyer's Responsibilities` |
| la | court_rules | `La. Code Jud. Conduct Canon 1` |
| ma | court_rules | `Mass. App. Ct. Rule 10.0` |
| md | court_rules | `Md. Rule 10-101` |
| me | court_rules | `Me. R. App. P. 1` |
| mi | court_rules | `Mich. Admin. Order No. 1968-2` |
| mn | court_rules | `Minn. R. Civ. App. P. 1` |
| ms | court_rules | `Miss. App. E-Filing Admin. P. 1` |
| mt | court_rules | `M. R. App. P. Form 1` |
| nc | court_rules | `Rules for Court-Ordered Arbitration, Rule 1` |
| nd | court_rules | `N.D. Admis. Prac. R. 1` |
| ne | court_rules | `Neb. Ct. R., Unauthorized Practice of Law: Statement of Intent` |
| nh | court_rules | `N.H. Cir. Ct. Dist. Div. R. 3.30` |
| nv | court_rules | `Nev. Civ. Traffic Infraction R. 1.3` |
| ny | court_rules | `22 NYCRR § 100.0` |
| oh | court_rules | `Ohio App.R. 1` |
| or | court_rules | `Or. Code Jud. Conduct R. 1.1` |
| pa | court_rules | `PA. R. Ct. 101` |
| pr | court_rules | `Canon 1 de Etica Judicial` |
| ri | court_rules | `Dist.R.Civ.P. 1` |
| sc | court_rules | `Rule 1.0, Rule 407, SCACR` |
| tn | court_rules | `Tenn. Ct. App. R. 1` |
| tx | court_rules | `Tex. R. App. P. 1` |
| ut | court_rules | `Utah R. Ct.-Annexed ADR 101` |
| va | court_rules | `Va. Sup. Ct. R. 11:1` |
| wa | court_rules | `APR 1` |
| wi | court_rules | `SCR 10.01` |
| wv | court_rules | `W. Va. Code Jud. Conduct R. 1.1` |
| wy | court_rules | `Bylaws of the Wyoming State Bar, Rule 1` |
| federal | enforcement_action | `In re OCR Concludes 2018 with All-Time Record Year for HIPAA Enforcement, HHS OCR Resolution Agreement` |
| federal | executive_order | `80 FR 819` |
| federal | faq | `HHS OCR HIPAA FAQ 1040` |
| ak | guidance | `AK Insurance Bulletin B89-01` |
| al | guidance | `AL Insurance Bulletin No. 2009-01` |
| ar | guidance | `AR Insurance Bulletin 4-74` |
| az | guidance | `AZ Circular Letter 1981-02` |
| ca | guidance | `CA Bulletin 1980-06` |
| ct | guidance | `CT Insurance Bulletin CL-1-07` |
| dc | guidance | `DC DISB Bulletin 04-IB-003-6/1` |
| de | guidance | `DE Auto Bulletin No. 10` |
| federal | guidance | `BIS Advisory Opinion, 05/06/03: Remotely sensed imagery` |
| fl | guidance | `FL OIR Informational Memorandum OIR-14-01M` |
| ga | guidance | `GA Bulletin 2020-EX-01` |
| hi | guidance | `HI Commissioner's Memorandum 2002-10R` |
| ia | guidance | `IA Bulletin 00-04` |
| id | guidance | `ID Insurance Bulletin 16-05` |
| il | guidance | `IL Company Bulletin 2011-05` |
| in | guidance | `IN Bulletin 1` |
| ks | guidance | `KS Bulletin 1987-06` |
| ky | guidance | `KY Insurance Advisory Opinion 1998-01` |
| ma | guidance | `MA Bulletin 1997-01` |
| md | guidance | `MD Insurance Bulletin 00-01` |
| me | guidance | `ME Insurance Bulletin 108` |
| mi | guidance | `MI DIFS Bulletin 2006-04-INS` |
| mn | guidance | `MN Commerce Administrative Bulletin 2010-4` |
| mo | guidance | `MO Insurance Bulletin 2001-04` |
| ms | guidance | `MS Insurance Bulletin 80-1` |
| mt | guidance | `MT CSI Advisory Memorandum of 1995-10-10` |
| nc | guidance | `NC DOI Bulletin 15-B-01` |
| nd | guidance | `ND Insurance Department Bulletin 1 (1969)` |
| ne | guidance | `NE Insurance Company Bulletin CB-4` |
| nh | guidance | `NH Insurance Department Bulletin INS 02-023-AB` |
| nj | guidance | `NJ DOBI Bulletin 2001-01` |
| nm | guidance | `NM Insurance Bulletin 2014-002` |
| nv | guidance | `NV Bulletin 00-001` |
| ny | guidance | `NY Insurance Circular Letter No. 3 (2026)` |
| oh | guidance | `OH Bulletin 1963-35` |
| ok | guidance | `OK Bulletin 2014-01` |
| or | guidance | `OR DFR Bulletin 1970-04` |
| pr | guidance | `PR Carta Circular Núm. 1-126-56` |
| ri | guidance | `RI Insurance Bulletin 2002-11` |
| sc | guidance | `SC Insurance Bulletin 1999-01` |
| sd | guidance | `SD Insurance Bulletin 1998-05` |
| tn | guidance | `TN Insurance Bulletin (1983-10-27)` |
| tx | guidance | `TDI Commissioner's Bulletin B-0001-00` |
| ut | guidance | `UT Insurance Bulletin 86-5` |
| va | guidance | `VA Administrative Letter 1979-20` |
| vt | guidance | `VT Insurance Bulletin #100` |
| wa | guidance | `WA OIC Advisory Notice (2020)` |
| wi | guidance | `WI OCI Bulletin (1996-06-06)` |
| wv | guidance | `WV Insurance Bulletin No. 20-01` |
| wy | guidance | `WY Insurance Bulletin 1-2026` |
| federal | guideline | `U.S.S.G. § 1A1.1` |
| federal | irs_announcement | `Announcement 2015-1` |
| federal | irs_notice | `Notice 2015-10` |
| federal | irs_rev_proc | `Rev. Proc. 2015-12` |
| federal | irs_rev_rul | `Rev. Rul. 2015-1` |
| federal | memorandum | `80 FR 3135` |
| federal | presidential_document | `80 FR 3461` |
| federal | proclamation | `80 FR 823` |
| co | regulations | `1 CCR 301-47` |
| de | regulations | `4 Del. Admin. Code § 203` |
| federal | regulations | `36 C.F.R. § 1206.70 (2026)` |
| id | regulations | `IDAPA 11.04.01.232` |
| il | regulations | `35 Ill. Adm. Code 604.125` |
| ky | regulations | `201 KAR 7:070` |
| md | regulations | `COMAR 10.07.01.37` |
| me | regulations | `94-089 Ch. 815` |
| mn | regulations | `Minn. R. 1260.0700` |
| nm | regulations | `6.75.5.9 NMAC` |
| oh | regulations | `Ohio Admin. Code 4783-1-08` |
| sc | regulations | `S.C. Code Regs. 3-304.13` |
| sd | regulations | `S.D. Admin. R. 20:08:04:113` |
| tx | regulations | `10 Tex. Admin. Code § 10.1001` |
| va | regulations | `12 Va. Admin. Code § 5-31-1800` |
| wa | regulations | `WAC 392-138-130` |
| wi | regulations | `Wis. Admin. Code Pod § 3.01` |
| federal | ruling | `DDTC Commodity Jurisdiction Determination: Molded Spacer, Part Number JSFW1 (Sanders Industries Holdings, Inc), 2010-08-20` |
| ak | statutes | `Alaska Stat. § 10.06.005` |
| al | statutes | `Ala. Code § 10A-10-1.01` |
| ar | statutes | `Ark. Code Ann. § 10-2-101` |
| az | statutes | `A.R.S. § 10-1001` |
| ca | statutes | `Cal. BPC § 1` |
| co | statutes | `C.R.S. § 10-10-101` |
| ct | statutes | `Conn. Gen. Stat. § 10-1` |
| dc | statutes | `D.C. Code § 10-1031` |
| de | statutes | `10 Del. C. § 1317` |
| federal | statutes | `10 U.S.C. § 10001 (2024)` |
| fl | statutes | `Fla. Stat. § 10.001` |
| hi | statutes | `Haw. Rev. Stat. § 121-1` |
| ia | statutes | `Iowa Code § 100A.1` |
| id | statutes | `Idaho Code § 10-1106` |
| il | statutes | `105 ILCS 105/1` |
| in | statutes | `Ind. Code § 10-10.5-1-1` |
| ks | statutes | `K.S.A. § 10-1001` |
| ky | statutes | `KRS § 11A.001` |
| la | statutes | `La. Ch. Code art. 100` |
| ma | statutes | `Mass. Gen. Laws ch. 237, sec. 1` |
| md | statutes | `Md. Code, Alcoholic Beverages and Cannabis § 10-1001` |
| me | statutes | `10 M.R.S. § 9001` |
| mi | statutes | `Mich. Comp. Laws § 10.71` |
| mn | statutes | `Minn. Stat. § 103A.001` |
| mo | statutes | `Mo. Rev. Stat. § 100.010` |
| ms | statutes | `Miss. Code Ann. § 11-11-1` |
| mt | statutes | `Mont. Code Ann. § 10-1-1001` |
| nd | statutes | `N.D. Cent. Code § 10-01.1-01` |
| ne | statutes | `Neb. Rev. Stat. § 10-1001` |
| nh | statutes | `N.H. Rev. Stat. § 31:1` |
| nj | statutes | `N.J. Stat. § 10:1-1` |
| nm | statutes | `N.M. Stat. § 10-10-1` |
| nv | statutes | `Nev. Rev. Stat. § 657.005` |
| ny | statutes | `N.Y. ABC Law § 150` |
| oh | statutes | `Ohio Rev. Code § 1101.01` |
| ok | statutes | `Okla. Stat. tit. 10A, § 10A-1-1-101` |
| or | statutes | `ORS § 100.005` |
| pa | statutes | `11 Pa.C.S. § 10101` |
| pr | statutes | `Ley Pol. Púb. Amb. P.R. art. 1` |
| ri | statutes | `R.I. Gen. Laws § 10-10-1` |
| sc | statutes | `S.C. Code Ann. § 10-11-10` |
| sd | statutes | `S.D. Codified Laws § 10-10-1` |
| tn | statutes | `Tenn. Code Ann. § 10-1-101` |
| tx | statutes | `Tex. Agriculture Code § 101.001` |
| ut | statutes | `Utah Code § 10-11-1` |
| va | statutes | `Va. Code Ann. § 10.1-2200` |
| vt | statutes | `10APPENDIX V.S.A. § 1` |
| wa | statutes | `RCW 10.01.030` |
| wi | statutes | `Wis. Stat. § 100.01` |
| wv | statutes | `W. Va. Code § 10-1A-1` |
| wy | statutes | `Wyo. Stat. § 10-1-101` |
| federal | treaty | `U.S.-Armenia Income Tax Treaty` |

## 7. Cross-reference coverage by corpus

| Corpus | rows | total USC edges | total rows w/ USC xref |
|---|---:|---:|---:|
| statutes | 1,997,490 | 153,975 | 56,139 (2.8%) |
| regulations | 885,121 | 64,109 | 34,518 (3.9%) |
| guidance | 25,461 | 6,380 | 2,193 (8.6%) |
| ruling | 7,248 | 914 | 381 (5.3%) |
| constitutions | 13,382 | 0 | 0 (0.0%) |
| court_rules | 43,809 | 0 | 0 (0.0%) |
| administrative_guidance | 11 | 0 | 0 (0.0%) |
| enforcement_action | 140 | 0 | 0 (0.0%) |
| executive_order | 738 | 0 | 0 (0.0%) |
| faq | 444 | 0 | 0 (0.0%) |
| guideline | 302 | 0 | 0 (0.0%) |
| irs_announcement | 83 | 0 | 0 (0.0%) |
| irs_notice | 759 | 0 | 0 (0.0%) |
| irs_rev_proc | 377 | 0 | 0 (0.0%) |
| irs_rev_rul | 245 | 0 | 0 (0.0%) |
| memorandum | 401 | 0 | 0 (0.0%) |
| presidential_document | 655 | 0 | 0 (0.0%) |
| proclamation | 1,832 | 0 | 0 (0.0%) |
| treaty | 119 | 0 | 0 (0.0%) |

## 8. Lineage-status load (rows needing Tier-3 handling)

Across the snapshot, **10,395 rows** carry a disposition status (renumbered/transferred/recodified/superseded/omitted). Of **1,434 `renumbered`** rows, **372 (25.9%)** state their successor inline in the text → deterministic lineage edge. Transferred/omitted need the `Editorial Notes / Codification` parser.

## 9. Per-file summary (appendix)

| File | rows | act_id pop | unique | hier-complete | USC edges | statuses |
|---|---:|---:|:--:|---:|---:|---:|
| us_ak_constitutions.parquet | 243 | 100.0% | y | 0.0% | 0 | 1 |
| us_ak_court_rules.parquet | 763 | 100.0% | y | 0.0% | 0 | 2 |
| us_ak_guidance.parquet | 398 | 100.0% | y | 0.0% | 0 | 5 |
| us_ak_statutes.parquet | 17,935 | 100.0% | y | 100.0% | 2 | 3 |
| us_al_constitutions.parquet | 381 | 100.0% | y | 0.0% | 0 | 1 |
| us_al_court_rules.parquet | 870 | 100.0% | y | 0.0% | 0 | 2 |
| us_al_guidance.parquet | 207 | 100.0% | y | 0.0% | 0 | 3 |
| us_al_statutes.parquet | 45,984 | 100.0% | y | 100.0% | 848 | 3 |
| us_ar_constitutions.parquet | 513 | 100.0% | y | 0.0% | 0 | 2 |
| us_ar_guidance.parquet | 359 | 100.0% | y | 0.0% | 0 | 2 |
| us_ar_statutes.parquet | 36,936 | 100.0% | y | 100.0% | 1,266 | 2 |
| us_az_constitutions.parquet | 646 | 100.0% | y | 0.0% | 0 | 1 |
| us_az_court_rules.parquet | 1,718 | 100.0% | y | 0.0% | 0 | 1 |
| us_az_guidance.parquet | 199 | 100.0% | y | 0.0% | 0 | 2 |
| us_az_statutes.parquet | 22,674 | 100.0% | y | 100.0% | 17 | 3 |
| us_ca_constitutions.parquet | 362 | 100.0% | y | 0.0% | 0 | 1 |
| us_ca_court_rules.parquet | 1,521 | 100.0% | y | 0.0% | 0 | 3 |
| us_ca_guidance.parquet | 463 | 100.0% | y | 0.0% | 0 | 3 |
| us_ca_statutes.parquet | 161,566 | 100.0% | y | 28.0% | 2,813 | 2 |
| us_co_constitutions.parquet | 424 | 100.0% | y | 0.0% | 0 | 2 |
| us_co_regulations.parquet | 610 | 100.0% | y | 0.0% | 0 | 1 |
| us_co_statutes.parquet | 34,231 | 100.0% | y | 0.0% | 1,625 | 3 |
| us_ct_constitutions.parquet | 174 | 100.0% | y | 0.0% | 0 | 1 |
| us_ct_court_rules.parquet | 1,723 | 100.0% | y | 0.0% | 0 | 2 |
| us_ct_guidance.parquet | 369 | 100.0% | y | 0.0% | 0 | 2 |
| us_ct_statutes.parquet | 16,082 | 100.0% | y | 100.0% | 55 | 3 |
| us_dc_administrative_guidance.parquet | 1 | 100.0% | y | 0.0% | 0 | 1 |
| us_dc_court_rules.parquet | 1,128 | 100.0% | y | 0.0% | 0 | 4 |
| us_dc_guidance.parquet | 23 | 100.0% | y | 0.0% | 0 | 1 |
| us_dc_statutes.parquet | 23,694 | 100.0% | y | 97.2% | 0 | 8 |
| us_de_constitutions.parquet | 225 | 100.0% | y | 0.0% | 0 | 2 |
| us_de_court_rules.parquet | 1,385 | 100.0% | y | 0.0% | 0 | 3 |
| us_de_guidance.parquet | 303 | 100.0% | y | 0.0% | 0 | 5 |
| us_de_regulations.parquet | 1,164 | 100.0% | y | 0.0% | 0 | 4 |
| us_de_statutes.parquet | 21,649 | 100.0% | y | 97.0% | 1,597 | 3 |
| us_federal_administrative_guidance.parquet | 10 | 100.0% | y | 0.0% | 0 | 1 |
| us_federal_constitutions.parquet | 74 | 100.0% | y | 0.0% | 0 | 1 |
| us_federal_court_rules.parquet | 589 | 100.0% | y | 0.0% | 0 | 2 |
| us_federal_enforcement_action.parquet | 140 | 100.0% | y | 0.0% | 0 | 1 |
| us_federal_executive_order.parquet | 738 | 100.0% | y | 0.0% | 0 | 1 |
| us_federal_faq.parquet | 444 | 100.0% | y | 0.0% | 0 | 1 |
| us_federal_guidance.parquet | 12,364 | 100.0% | y | 0.0% | 6,380 | 5 |
| us_federal_guideline.parquet | 302 | 100.0% | y | 0.0% | 0 | 1 |
| us_federal_irs_announcement.parquet | 83 | 100.0% | y | 100.0% | 0 | 1 |
| us_federal_irs_notice.parquet | 759 | 100.0% | y | 100.0% | 0 | 1 |
| us_federal_irs_rev_proc.parquet | 377 | 100.0% | y | 100.0% | 0 | 1 |
| us_federal_irs_rev_rul.parquet | 245 | 100.0% | y | 100.0% | 0 | 1 |
| us_federal_memorandum.parquet | 401 | 100.0% | y | 0.0% | 0 | 1 |
| us_federal_presidential_document.parquet | 655 | 100.0% | y | 0.0% | 0 | 1 |
| us_federal_proclamation.parquet | 1,832 | 100.0% | y | 0.0% | 0 | 1 |
| us_federal_regulations.parquet | 582,054 | 100.0% | N | 35.9% | 64,077 | 2 |
| us_federal_ruling.parquet | 7,248 | 100.0% | y | 15.4% | 914 | 2 |
| us_federal_statutes.parquet | 54,853 | 100.0% | y | 99.9% | 128,062 | 7 |
| us_federal_treaty.parquet | 119 | 100.0% | y | 0.0% | 0 | 1 |
| us_fl_constitutions.parquet | 217 | 100.0% | y | 0.0% | 0 | 1 |
| us_fl_court_rules.parquet | 936 | 100.0% | y | 0.0% | 0 | 1 |
| us_fl_guidance.parquet | 43 | 100.0% | y | 0.0% | 0 | 1 |
| us_fl_statutes.parquet | 24,866 | 100.0% | y | 0.0% | 0 | 1 |
| us_ga_constitutions.parquet | 287 | 100.0% | y | 0.0% | 0 | 2 |
| us_ga_court_rules.parquet | 1,174 | 100.0% | y | 0.0% | 0 | 4 |
| us_ga_guidance.parquet | 66 | 100.0% | y | 0.0% | 0 | 1 |
| us_hi_constitutions.parquet | 171 | 100.0% | y | 0.0% | 0 | 2 |
| us_hi_court_rules.parquet | 1,259 | 100.0% | y | 0.0% | 0 | 3 |
| us_hi_guidance.parquet | 168 | 100.0% | y | 0.0% | 0 | 2 |
| us_hi_statutes.parquet | 19,197 | 100.0% | y | 100.0% | 88 | 3 |
| us_ia_constitutions.parquet | 190 | 100.0% | y | 0.0% | 0 | 1 |
| us_ia_court_rules.parquet | 1,294 | 100.0% | y | 0.0% | 0 | 2 |
| us_ia_guidance.parquet | 83 | 100.0% | y | 0.0% | 0 | 2 |
| us_ia_statutes.parquet | 28,223 | 100.0% | y | 0.0% | 871 | 3 |
| us_id_constitutions.parquet | 240 | 100.0% | y | 0.0% | 0 | 1 |
| us_id_court_rules.parquet | 766 | 100.0% | y | 0.0% | 0 | 3 |
| us_id_guidance.parquet | 75 | 100.0% | y | 0.0% | 0 | 2 |
| us_id_regulations.parquet | 8,551 | 100.0% | y | 0.0% | 0 | 1 |
| us_id_statutes.parquet | 22,754 | 100.0% | y | 100.0% | 156 | 2 |
| us_il_constitutions.parquet | 170 | 100.0% | y | 0.0% | 0 | 1 |
| us_il_court_rules.parquet | 839 | 100.0% | y | 0.0% | 0 | 1 |
| us_il_guidance.parquet | 158 | 100.0% | y | 0.0% | 0 | 2 |
| us_il_regulations.parquet | 53,584 | 100.0% | N | 100.0% | 0 | 1 |
| us_il_statutes.parquet | 72,456 | 100.0% | y | 0.0% | 70 | 2 |
| us_in_constitutions.parquet | 196 | 100.0% | y | 0.0% | 0 | 2 |
| us_in_court_rules.parquet | 879 | 100.0% | y | 0.0% | 0 | 4 |
| us_in_guidance.parquet | 281 | 100.0% | y | 0.0% | 0 | 2 |
| us_in_statutes.parquet | 83,148 | 100.0% | y | 100.0% | 5 | 3 |
| us_ks_constitutions.parquet | 229 | 100.0% | y | 0.0% | 0 | 1 |
| us_ks_court_rules.parquet | 434 | 100.0% | y | 0.0% | 0 | 3 |
| us_ks_guidance.parquet | 79 | 100.0% | y | 0.0% | 0 | 2 |
| us_ks_statutes.parquet | 24,361 | 100.0% | y | 0.0% | 477 | 3 |
| us_ky_constitutions.parquet | 274 | 100.0% | y | 0.0% | 0 | 1 |
| us_ky_guidance.parquet | 232 | 100.0% | y | 0.0% | 0 | 3 |
| us_ky_regulations.parquet | 4,865 | 100.0% | N | 100.0% | 0 | 1 |
| us_ky_statutes.parquet | 20,894 | 100.0% | y | 0.0% | 598 | 3 |
| us_la_constitutions.parquet | 328 | 100.0% | y | 0.0% | 0 | 1 |
| us_la_court_rules.parquet | 481 | 100.0% | y | 0.0% | 0 | 4 |
| us_la_statutes.parquet | 43,512 | 100.0% | y | 0.0% | 119 | 3 |
| us_ma_constitutions.parquet | 104 | 100.0% | y | 0.0% | 0 | 2 |
| us_ma_court_rules.parquet | 970 | 100.0% | y | 0.0% | 0 | 3 |
| us_ma_guidance.parquet | 417 | 100.0% | y | 0.0% | 0 | 4 |
| us_ma_statutes.parquet | 23,152 | 100.0% | y | 0.0% | 305 | 3 |
| us_md_constitutions.parquet | 312 | 100.0% | y | 0.0% | 0 | 1 |
| us_md_court_rules.parquet | 1,220 | 100.0% | y | 100.0% | 0 | 1 |
| us_md_guidance.parquet | 675 | 100.0% | y | 0.0% | 0 | 3 |
| us_md_regulations.parquet | 12,863 | 100.0% | N | 100.0% | 0 | 1 |
| us_md_statutes.parquet | 39,552 | 100.0% | y | 0.0% | 498 | 2 |
| us_me_constitutions.parquet | 153 | 100.0% | y | 0.0% | 0 | 1 |
| us_me_court_rules.parquet | 722 | 100.0% | y | 0.0% | 0 | 3 |
| us_me_guidance.parquet | 228 | 100.0% | y | 0.0% | 0 | 3 |
| us_me_regulations.parquet | 1,718 | 100.0% | N | 0.0% | 0 | 1 |
| us_me_statutes.parquet | 25,316 | 100.0% | y | 100.0% | 6 | 3 |
| us_mi_constitutions.parquet | 307 | 100.0% | y | 0.0% | 0 | 1 |
| us_mi_court_rules.parquet | 1,025 | 100.0% | y | 0.0% | 0 | 2 |
| us_mi_guidance.parquet | 145 | 100.0% | y | 0.0% | 0 | 2 |
| us_mi_statutes.parquet | 40,658 | 100.0% | y | 0.0% | 14 | 3 |
| us_mn_constitutions.parquet | 138 | 100.0% | y | 0.0% | 0 | 1 |
| us_mn_court_rules.parquet | 958 | 100.0% | y | 0.0% | 0 | 1 |
| us_mn_guidance.parquet | 34 | 100.0% | y | 0.0% | 0 | 2 |
| us_mn_regulations.parquet | 15,447 | 100.0% | N | 0.0% | 0 | 1 |
| us_mn_statutes.parquet | 27,747 | 100.0% | y | 0.0% | 38 | 3 |
| us_mo_constitutions.parquet | 445 | 100.0% | y | 0.0% | 0 | 1 |
| us_mo_guidance.parquet | 106 | 100.0% | y | 0.0% | 0 | 1 |
| us_mo_statutes.parquet | 29,309 | 100.0% | y | 0.0% | 553 | 2 |
| us_ms_constitutions.parquet | 318 | 100.0% | y | 0.0% | 0 | 1 |
| us_ms_court_rules.parquet | 794 | 100.0% | y | 0.0% | 0 | 2 |
| us_ms_guidance.parquet | 240 | 100.0% | y | 0.0% | 0 | 4 |
| us_ms_statutes.parquet | 158,688 | 100.0% | y | 100.0% | 354 | 3 |
| us_mt_constitutions.parquet | 196 | 100.0% | y | 0.0% | 0 | 1 |
| us_mt_court_rules.parquet | 238 | 100.0% | y | 0.0% | 0 | 2 |
| us_mt_guidance.parquet | 149 | 100.0% | y | 0.0% | 0 | 2 |
| us_mt_statutes.parquet | 30,514 | 100.0% | y | 100.0% | 28 | 3 |
| us_nc_constitutions.parquet | 155 | 100.0% | y | 0.0% | 0 | 1 |
| us_nc_court_rules.parquet | 495 | 100.0% | y | 0.0% | 0 | 4 |
| us_nc_guidance.parquet | 120 | 100.0% | y | 0.0% | 0 | 1 |
| us_nd_constitutions.parquet | 203 | 100.0% | y | 0.0% | 0 | 2 |
| us_nd_court_rules.parquet | 2,246 | 100.0% | y | 0.0% | 0 | 4 |
| us_nd_guidance.parquet | 235 | 100.0% | y | 0.0% | 0 | 4 |
| us_nd_statutes.parquet | 29,042 | 100.0% | y | 100.0% | 19 | 3 |
| us_ne_constitutions.parquet | 448 | 100.0% | y | 0.0% | 0 | 1 |
| us_ne_court_rules.parquet | 734 | 100.0% | y | 0.0% | 0 | 3 |
| us_ne_guidance.parquet | 120 | 100.0% | y | 0.0% | 0 | 3 |
| us_ne_statutes.parquet | 25,997 | 100.0% | y | 6.5% | 16 | 4 |
| us_nh_constitutions.parquet | 157 | 100.0% | y | 0.0% | 0 | 2 |
| us_nh_court_rules.parquet | 970 | 100.0% | y | 0.0% | 0 | 3 |
| us_nh_guidance.parquet | 177 | 100.0% | y | 0.0% | 0 | 3 |
| us_nh_statutes.parquet | 25,375 | 100.0% | y | 0.0% | 449 | 3 |
| us_nj_constitutions.parquet | 216 | 100.0% | y | 0.0% | 0 | 1 |
| us_nj_guidance.parquet | 441 | 100.0% | y | 0.0% | 0 | 2 |
| us_nj_statutes.parquet | 55,993 | 100.0% | y | 100.0% | 14 | 3 |
| us_nm_constitutions.parquet | 299 | 100.0% | y | 0.0% | 0 | 2 |
| us_nm_guidance.parquet | 274 | 100.0% | y | 0.0% | 0 | 4 |
| us_nm_regulations.parquet | 13,270 | 100.0% | y | 100.0% | 0 | 1 |
| us_nm_statutes.parquet | 34,455 | 100.0% | y | 0.0% | 158 | 3 |
| us_nv_constitutions.parquet | 234 | 100.0% | y | 0.0% | 0 | 2 |
| us_nv_court_rules.parquet | 1,338 | 100.0% | y | 0.0% | 0 | 1 |
| us_nv_guidance.parquet | 199 | 100.0% | y | 0.0% | 0 | 3 |
| us_nv_statutes.parquet | 48,190 | 100.0% | y | 99.9% | 1,831 | 3 |
| us_ny_constitutions.parquet | 204 | 100.0% | y | 0.0% | 0 | 1 |
| us_ny_court_rules.parquet | 1,088 | 100.0% | y | 0.0% | 0 | 3 |
| us_ny_guidance.parquet | 1,199 | 100.0% | y | 0.0% | 0 | 2 |
| us_ny_statutes.parquet | 40,140 | 100.0% | y | 0.0% | 345 | 1 |
| us_oh_constitutions.parquet | 266 | 100.0% | y | 0.0% | 0 | 1 |
| us_oh_court_rules.parquet | 1,167 | 100.0% | y | 0.0% | 0 | 3 |
| us_oh_guidance.parquet | 112 | 100.0% | y | 0.0% | 0 | 1 |
| us_oh_regulations.parquet | 19,909 | 100.0% | N | 0.0% | 0 | 1 |
| us_oh_statutes.parquet | 33,161 | 100.0% | y | 100.0% | 0 | 1 |
| us_ok_constitutions.parquet | 545 | 100.0% | y | 0.0% | 0 | 2 |
| us_ok_guidance.parquet | 144 | 100.0% | y | 0.0% | 0 | 2 |
| us_ok_statutes.parquet | 35,329 | 100.0% | y | 0.0% | 113 | 3 |
| us_or_constitutions.parquet | 415 | 100.0% | y | 0.0% | 0 | 1 |
| us_or_court_rules.parquet | 632 | 100.0% | y | 0.0% | 0 | 3 |
| us_or_guidance.parquet | 92 | 100.0% | y | 0.0% | 0 | 1 |
| us_or_statutes.parquet | 36,202 | 100.0% | y | 100.0% | 14 | 3 |
| us_pa_constitutions.parquet | 186 | 100.0% | y | 0.0% | 0 | 1 |
| us_pa_court_rules.parquet | 1,722 | 100.0% | y | 0.0% | 0 | 1 |
| us_pa_statutes.parquet | 14,571 | 100.0% | y | 100.0% | 484 | 3 |
| us_pr_constitutions.parquet | 102 | 100.0% | y | 0.0% | 0 | 1 |
| us_pr_court_rules.parquet | 1,528 | 100.0% | y | 0.0% | 0 | 2 |
| us_pr_guidance.parquet | 1,641 | 100.0% | y | 0.0% | 0 | 2 |
| us_pr_statutes.parquet | 23,636 | 100.0% | y | 0.0% | 0 | 1 |
| us_ri_constitutions.parquet | 118 | 100.0% | y | 0.0% | 0 | 1 |
| us_ri_court_rules.parquet | 1,033 | 100.0% | y | 0.0% | 0 | 1 |
| us_ri_guidance.parquet | 134 | 100.0% | y | 0.0% | 0 | 1 |
| us_ri_statutes.parquet | 21,107 | 100.0% | y | 100.0% | 747 | 3 |
| us_sc_constitutions.parquet | 245 | 100.0% | y | 0.0% | 0 | 3 |
| us_sc_court_rules.parquet | 557 | 100.0% | y | 0.0% | 0 | 2 |
| us_sc_guidance.parquet | 319 | 100.0% | y | 0.0% | 0 | 2 |
| us_sc_regulations.parquet | 6,606 | 100.0% | y | 0.0% | 0 | 1 |
| us_sc_statutes.parquet | 29,947 | 100.0% | y | 100.0% | 295 | 3 |
| us_sd_constitutions.parquet | 294 | 100.0% | y | 0.0% | 0 | 3 |
| us_sd_guidance.parquet | 27 | 100.0% | y | 0.0% | 0 | 1 |
| us_sd_regulations.parquet | 28,988 | 100.0% | y | 0.0% | 32 | 5 |
| us_sd_statutes.parquet | 39,589 | 100.0% | y | 100.0% | 413 | 3 |
| us_tn_constitutions.parquet | 152 | 100.0% | y | 0.0% | 0 | 1 |
| us_tn_court_rules.parquet | 626 | 100.0% | y | 0.0% | 0 | 3 |
| us_tn_guidance.parquet | 173 | 100.0% | y | 0.0% | 0 | 1 |
| us_tn_statutes.parquet | 32,693 | 100.0% | y | 100.0% | 1,778 | 2 |
| us_tx_constitutions.parquet | 401 | 100.0% | y | 0.0% | 0 | 1 |
| us_tx_court_rules.parquet | 1,007 | 100.0% | y | 0.0% | 0 | 1 |
| us_tx_guidance.parquet | 1,254 | 100.0% | y | 0.0% | 0 | 1 |
| us_tx_regulations.parquet | 44,247 | 100.0% | y | 100.0% | 0 | 1 |
| us_tx_statutes.parquet | 122,535 | 100.0% | y | 0.0% | 2,586 | 3 |
| us_ut_constitutions.parquet | 189 | 100.0% | y | 0.0% | 0 | 1 |
| us_ut_court_rules.parquet | 919 | 100.0% | y | 0.0% | 0 | 2 |
| us_ut_guidance.parquet | 168 | 100.0% | y | 0.0% | 0 | 1 |
| us_ut_statutes.parquet | 25,880 | 100.0% | y | 54.8% | 0 | 1 |
| us_va_constitutions.parquet | 134 | 100.0% | y | 0.0% | 0 | 1 |
| us_va_court_rules.parquet | 358 | 100.0% | y | 0.0% | 0 | 2 |
| us_va_guidance.parquet | 89 | 100.0% | y | 0.0% | 0 | 1 |
| us_va_regulations.parquet | 22,396 | 100.0% | y | 100.0% | 0 | 2 |
| us_va_statutes.parquet | 33,857 | 100.0% | y | 98.0% | 1,289 | 2 |
| us_vt_constitutions.parquet | 120 | 100.0% | y | 0.0% | 0 | 1 |
| us_vt_guidance.parquet | 187 | 100.0% | y | 0.0% | 0 | 1 |
| us_vt_statutes.parquet | 23,521 | 100.0% | y | 100.0% | 826 | 3 |
| us_wa_constitutions.parquet | 282 | 100.0% | y | 0.0% | 0 | 2 |
| us_wa_court_rules.parquet | 1,182 | 100.0% | y | 0.0% | 0 | 3 |
| us_wa_guidance.parquet | 24 | 100.0% | y | 0.0% | 0 | 1 |
| us_wa_regulations.parquet | 51,026 | 100.0% | y | 100.0% | 0 | 2 |
| us_wa_statutes.parquet | 51,498 | 100.0% | y | 100.0% | 1,128 | 3 |
| us_wi_constitutions.parquet | 175 | 100.0% | y | 0.0% | 0 | 2 |
| us_wi_court_rules.parquet | 395 | 100.0% | y | 0.0% | 0 | 2 |
| us_wi_guidance.parquet | 232 | 100.0% | y | 0.0% | 0 | 3 |
| us_wi_regulations.parquet | 17,823 | 100.0% | y | 0.0% | 0 | 2 |
| us_wi_statutes.parquet | 18,158 | 100.0% | y | 0.0% | 1 | 3 |
| us_wv_constitutions.parquet | 209 | 100.0% | y | 0.0% | 0 | 1 |
| us_wv_court_rules.parquet | 1,116 | 100.0% | y | 0.0% | 0 | 3 |
| us_wv_guidance.parquet | 174 | 100.0% | y | 0.0% | 0 | 1 |
| us_wv_statutes.parquet | 25,664 | 100.0% | y | 0.0% | 685 | 3 |
| us_wy_constitutions.parquet | 316 | 100.0% | y | 0.0% | 0 | 3 |
| us_wy_court_rules.parquet | 1,010 | 100.0% | y | 0.0% | 0 | 4 |
| us_wy_guidance.parquet | 62 | 100.0% | y | 0.0% | 0 | 1 |
| us_wy_statutes.parquet | 20,999 | 100.0% | y | 100.0% | 319 | 7 |

