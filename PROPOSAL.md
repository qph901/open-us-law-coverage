# Proposal: Citation Parser & Resolver for Open US Law (parser-first, USC-commissioned)

## Summary

Build a **citation detection / parsing / normalization / resolution** subsystem over the `vaquill/open-us-law` dataset (snapshot **v2026.08**), commissioned on the US Code (USC) and validated against edition-pinned USLM XML. This is the **hard foundation** of a legal RAG system. Retrieval and generation come *after* we can reliably identify what law a citation refers to, with an auditable explanation.

The guiding rule for the whole system: **uncertainty about legal identity must be represented as data, never hidden inside ID-generation code.** The system must be able to say "these are the same provision," "strong evidence this was renumbered into that," or "cannot reliably establish continuity" — and keep those as materially different claims.

The architecture that serves that rule is a **two-layer source/interpretation split**:

- **CanonicalSourceRecord** — what the dataset told us. Lossless, immutable, zero legal interpretation of ours.
- **Versioned derived annotations** — what our parsers *believe*, separated from the source by an explicit versioned boundary: `SourceIdentityAnnotation`, `DocumentClassificationAnnotation`, `QualityAnnotation`, `SourceDocumentAssembly`, `DocumentAnatomy`, `HierarchyTree`, and (downstream) `CanonicalLegalDocument` / `LegalChunk` / `CitationEdge` / `LineageEdge`.

Every annotation carries its own `DerivedArtifactProvenance` (a multi-input DAG — see Data contracts) and can be regenerated without ever rewriting the source record. This gives uncertainty an explicit home and lets parsers improve without churning provenance.

**Status:** M0 (reconnaissance), **M0.5A (identity-collision analysis)**, **M0.5A.1 (collision-provenance + segment-order spike)**, and **M1A (the immutable `CanonicalSourceRecord` core)** are **complete** — see `reports/M0_recon.md`, `reports/M0_full_snapshot.md`, `reports/M0_act_id_stability.md`, `reports/M0.5A_identity_collisions.md`, `reports/M0.5A1_segment_provenance.md`, and `src/open_us_law_coverage/source_record.py`. The source-identity contract has frozen with the *snapshot-observed ordinal* caveat from M0.5A.1. The next build phase is **M1A.5** (the shared derived-artifact foundation: multi-input provenance DAG + `SourceIdentityAnnotation` / `DocumentClassificationAnnotation` / `QualityAnnotation` / `SourceDocumentAssembly`), the **CFR assembly layer** (CFR-A1 commissioning → CFR-A2 producer), and the **M0.5B** spikes (parallel), ending at the **M1B** semantic freeze → **M0.5C** (disposition extraction). This document is the single source of truth; it carries the design decisions converged during review — including the M1A.5/CFR/M0.5B review that folded assembly into the identity boundary — and supersedes any earlier sequencing and any one-record `ingest → CanonicalLegalDocument` framing. **One architecture only.**

---

## First success criterion (the thing to prove before any embeddings)

> Given any supported USC citation — appearing either as a user query or inside another legal section — the system can **detect** it, **parse** it into structured components, **normalize** it, **resolve** it to the correct Open US Law provision, and produce an **auditable explanation** of how the resolution was obtained.

With measured, version-pinned, USLM-backed: detection precision/recall, parsing accuracy, resolution top-1 accuracy, ambiguity rate, and unresolved rate.

If we prove this before introducing embeddings, we have built the difficult part rather than another vector-search pipeline.

---

## Non-goals (explicitly deferred — do not scope-creep)

- Vector/dense retrieval, rerankers, embedding-model selection.
- Defined-term semantic graph (`DefinitionMention` / `DefinitionEdge`).
- Authority-hierarchy / conflict reasoning (constitution vs statute, preemption, later-in-time).
- Graph-RAG expansion.
- Full 52-jurisdiction state coverage (federal pipeline must work end-to-end first).
- Automatic official-source URL recovery.
- Complex court-rule / agency-guidance semantics.

These are real and important; they belong in later layers, not the parser MVP.

**Additional non-goals for the current (M0.5→M1) phase:** no embeddings/vector DB/reranker; no general state citation grammars; no full CA/state coverage (only a small CA commissioning sample runs end-to-end); no *resolved* `LineageEdge` before M3; no official-source URL recovery; no live/current USLM at runtime; **no renaming of `CanonicalLegalDocument` yet** (see Terminology).

---

## Prerequisites (human actions — an agent cannot do these)

1. **Accept the dataset terms.** `vaquill/open-us-law` is gated on Hugging Face; a human must accept conditions and provide an HF access token to the environment.
2. **Pin the snapshot(s).** Confirm the exact snapshot in use (target: `v2026.08`) and record it. Retain the adjacent snapshot (`v2026.07`) — snapshot retention is a **correctness** dependency, not eval convenience (see Cross-cutting invariants).
3. **Provide the USLM oracle.** Download OLRC USLM XML for the USC, **edition-pinned to the release at or before the snapshot's content date** (OLRC keys USC releases to public-law numbers) for M0.5B1. Record the exact USLM edition/date used.
4. **Provide the eCFR oracle.** Acquire **edition-pinned eCFR** for the CFR-A1 commissioning set, matched to the v2026.08 content date — eCFR exposes point-in-time versions, so pin to the release at or before the snapshot, **not** "current." Record the edition/date as a provenance input. Both USLM and eCFR are **at most edition-pinned build-time oracles** (recorded as provenance inputs), never query-runtime dependencies.
5. **Confirm network access** for the agent's environment to Hugging Face, govinfo.gov, and eCFR (or stage the files locally). Confirm both oracles are staged locally before the milestones that consume them.
6. **Point at the existing codebase** if this extends prior marker-class parsing work; adapt conventions accordingly rather than starting greenfield.

---

## What M0 established (recon findings that anchor the design)

M0 loaded the real v2026.08 Parquet (full 229-file / 2,978,617-row snapshot) and diffed `v2026.07 → v2026.08`. The findings below replace the earlier "assumptions to test" — the production design is grounded in these, not in the dataset card.

- **Uniform 24-column schema across all 229 files.** One normalizer handles every corpus and jurisdiction.
- **No predecessor/successor crosswalk column exists anywhere.** Lineage across renumber/transfer/recodify must be **inferred**, not read from a field. The only lineage-adjacent signals are `act_status`, `cross_references_usc/cfr`, `public_laws_referenced`, and disposition prose in the text.
- **`act_id` is a normalized, namespaced citation** (`USC_T42_C21_S1983`, `STATE_AK_…`, `SCONST_AK_…`). It is 100% populated in every corpus and is a good stable-source seed — **but it is NOT unique within the federal regulations file** (a genuine collision). Bare `act_id` semantics are therefore not universal; identity must go through a corpus-specific strategy (drove M0.5A).
- **`act_id` is stable across the v2026.07→v2026.08 transition**: no `act_id` was ever removed or reissued, and thousands survive text amendment → viable Tier-1 identity seed. **Caveat:** the USC `text` field bundles a volatile editorial-notes apparatus, so `text_hash` over raw `text` overstates real amendment (~48% of USC rows "changed," almost all editorial-note growth). The operative body must be hashed separately — this directly motivates the anatomy work (M0.5B1) and the identity correction below.
- **Flat hierarchy columns are not reliable across jurisdictions.** California leaves `title_number` null on ~70% of rows (it namespaces by *code*, e.g. `Cal. BPC`); the real hierarchy lives in `breadcrumb` / `display_path`. USC and AK flat columns are ~100% clean.
- **USC cross-references ship pre-extracted** (`cross_references_usc` as `"title:section"` arrays), dense on federal USC and sparse elsewhere, plus `public_laws_referenced`. A head start and an oracle for M4 — but **field-present rate is not a recall floor** (see Cross-cutting invariants).
- **Disposition often lives in the text.** ~10,395 rows carry a disposition status; many `renumbered` rows state their successor inline (`[§2010. Renumbered §321]`), giving a deterministic lineage edge; `transferred`/`omitted` history sits in `Editorial Notes / Codification` prose and needs a dedicated parser.

---

## Settled architecture (do not reopen)

Two invariants govern everything:

1. **Identity, content, and order are orthogonal.** `source_record_id`, `raw_text_hash`/`segment_fingerprint`, `segment_ordinal`, and `legal_id` each answer a different question; none substitutes for another.
2. **Source facts vs. parser-derived interpretation are separated by a versioned boundary.** Preserve Open US Law's assertions verbatim in the immutable record; put *our interpretation of those assertions* in versioned annotations.

### Locked invariants (do not reopen)

These are settled; code that breaks them defeats the point of the project.

- **Identity, content, and order are orthogonal:** `source_record_id` (physical) / `raw_text_hash` (content) / `segment_ordinal` (snapshot-observed order, non-durable) / `legal_id` (legal entity).
- **Source vs interpretation is a versioned boundary:** source provenance is immutable; identity assignments are versioned and evidence-bearing; promoted `legal_id`s are durable references corrected **additively** (`superseded_identity` / `merged_into` / `split_into` / `alias_of` / `erroneous_assignment`), never overwritten. `legal_id` is **not** in the immutability invariant.
- **Layer order:** `CanonicalSourceRecord[] → SourceIdentityAnnotation (group) → SourceDocumentAssembly (compose) → DocumentAnatomy (parse) → LegalDocumentView`. **Assembly precedes anatomy**; the continuation signal that composes rows is raw-text assembly evidence, not anatomy. Anatomy is an *optional validator* of a candidate assembly, never its source.
- **Oracles are build-time only:** USLM (anatomy) and eCFR (CFR assembly) are at most edition-pinned **build-time** oracles, recorded as provenance inputs — never query-runtime dependencies.
- **Never deduplicate `CanonicalSourceRecord`.** Duplicates stay in the immutable core; annotations/assembly record the relationship and pick one copy for semantic text.

The single reconciled pipeline (this is the one pipeline — no other diagram in this document supersedes it):

```
Open US Law snapshot-set (Parquet, gated)        + USLM oracle (edition-pinned)
        │
CanonicalSourceRecord            ← immutable / lossless (raw_text + 24 source fields verbatim)
        │
── versioned parser boundary ──────────────
        │
versioned derived annotations
   ├── SourceIdentityAnnotation        (group/characterize only; fed by M0.5A.1)
   ├── DocumentClassificationAnnotation
   ├── QualityAnnotation               (first producer: duplicate_row only)
   ├── SourceDocumentAssembly          (compose members of an identity group → assembled_text)
   ├── DocumentAnatomy                 (operative vs editorial spans; USLM-aligned for USC)
   └── HierarchyTree / HierarchyNode[]
        │
CanonicalLegalDocument / LegalEntity mapping   (source_record_id --identified_as--> legal_id;
                                                 legal_id attaches to the assembly, not the row)
        │
LegalChunk
        │
CitationMention / LineageMention
        │
Hierarchy-aware Resolver → Alias Index → Lineage-aware Resolver
        │
CitationEdge / LineageEdge   (auditable; rule vs model distinguishable)
        │
Retrieval artifacts (exact-citation index first; BM25/dense LATER)
        │
RAG (LATER)
```

**The boundary test:** nothing in `CanonicalSourceRecord` may change because our identity rules, anatomy parser, hierarchy parser, duplicate detection, Federal-Register interpretation, or a quality detector improved. If any such change would require rewriting the source record, the boundary was violated. Rebuilding any derived layer (new anatomy parser, new chunker, new embedding model) must have **zero** effect on `source_record_id` / `raw_text_hash` / `legal_id`.

---

## Identity: four orthogonal concepts

**Decision adopted this round:** `legal_id` must **not** derive from `raw_text_hash`, citation text, or any content/interpretation. M0 proved USC `raw_text` changes when editorial apparatus changes even though the provision does not; binding identity to content recreates that churn. Keep four concerns orthogonal:

| Concept | Question it answers | Layer | Stability |
|---|---|---|---|
| `source_record_id` | which physical row in which snapshot? | immutable core | snapshot-local (nothing durable depends on it across snapshots) |
| `segment_fingerprint` | which exact segment content? | content-addressed | changes iff bytes change (= representation identity, **not** logical continuity) |
| `segment_ordinal` | in what observed order was this row presented? | ordering annotation | observational; may be snapshot-only |
| `legal_id` | which stable legal/source object? | derived, established later | cross-snapshot where continuity is supported |

`source_identity_key` is **our current interpretation** of how source fields jointly identify an object → it lives in `SourceIdentityAnnotation`, never in the immutable core, and never as a durable foreign key (see the durable-FK rule). The earlier `document_id`/`version_id` framing is subsumed: the snapshot-local physical address is now `source_record_id`; durable references anchor to it, not to a separate document address.

### Stability tiers (how `legal_id` is assigned)

- **Proven stable source** — where M0/M0.5 prove source identity is populated, unique in its namespace, and fixed under text-only amendment, seed `legal_id` from that source identity. `stability_class = proven`.
- **Snapshot-local** — a row with no trustworthy stable identifier does **not** manufacture identity from its citation. It is addressed by its `source_record_id`; `stability_class = snapshot_local`. Represent the gap honestly.
- **Cross-snapshot lineage (inferred)** — for `renumbered` / `transferred` / `recodified` rows, where source identity is expected to break, infer lineage from multiple signals (high-similarity operative-text hash, hierarchy match, section-number transition, status flag, neighbor continuity, explicit disposition language). Record a `LineageEdge` with method/confidence/evidence. **Do not merge** A and B into one `legal_id` on similarity alone; link via `lineage_id`, keep distinct `legal_id`s.
- **USC bonus:** cross-check source-identity continuity against the USLM `@identifier`; divergence flags a likely renumbering and doubles as free lineage evidence and resolver validation.

### Source identity is corpus-specific

The federal-regulation `act_id` collision proves bare `act_id` is not a universal key. Identity resolution goes through a versioned strategy, never a hardcoded key:

```
SourceIdentityStrategy          # one per corpus, versioned; emits into SourceIdentityAnnotation
    identity_key(record)      -> source_identity_key
    namespace(record)         -> namespace tuple
    stability_class(record)   -> proven | snapshot_local | unknown
    confidence(record)
```

`legal_id = (state, corpus, act_id)` etc. is emitted **by a strategy**, never a universal equation. Several strategies may currently emit identical-looking tuples; the strategy name preserves the semantics and the migration path. No shared base class or DB schema may assume `act_id` alone is a key. USC may return `(state, corpus, act_id)`; CFR/FR require the segment discriminator determined by M0.5A/A.1. Note `jurisdiction` is uniformly `"US"`; `state` is the real discriminator.

### The durable-foreign-key rule

Durable references between derived artifacts anchor to **`source_record_id`** (plus the artifact's own producer/version) — **never** to `source_identity_key`, which changes when a strategy improves. Stable legal entities get a `legal_id` later, with an explicit, versioned, evidence-bearing mapping:

```
source_record_id --identified_as--> legal_id
```

This keeps a mistaken identity strategy from corrupting provenance. `source_record_id` = physical truth; `source_identity_key` = current identity interpretation; `legal_id` = stable project-level legal entity once established. These never collapse into one concept.

**Promoted `legal_id`s are corrected additively, never overwritten.** Once a `legal_id` is published as a durable reference, a later correction is recorded as a new evidence-bearing fact — `superseded_identity`, `merged_into`, `split_into`, `alias_of`, or `erroneous_assignment` — rather than by mutating or deleting the original assignment. This is why `legal_id` sits *outside* the immutability invariant (it can be corrected) yet stays a *durable* reference (corrections are additive, so old references never dangle or silently repoint).

---

## Data contracts

The split is the point: `CanonicalSourceRecord` is lossless and immutable and carries no conclusion of ours; everything else is derived and carries `DerivedArtifactProvenance`. Concrete field lists; adapt names to the existing codebase.

### `CanonicalSourceRecord` — immutable (lossless)
```
source_record_id      # = hash(snapshot_version, source_file_checksum, physical_row_ordinal)
snapshot_version
source_file
source_file_checksum
physical_row_ordinal
original_columns      # all 24 Open US Law fields, verbatim (incl. act_id, citation,
                      #   citation_short, state, jurisdiction, document_type, title_number,
                      #   title_name, chapter, chapter_name, section_number, section_title,
                      #   breadcrumb, display_path, act_status, word_count, source_url,
                      #   last_amended_year, subsection_count, cross_references_usc,
                      #   cross_references_cfr, public_laws_referenced, year)
raw_text              # = the source `text` field, immutable
raw_text_hash         # = hash(raw_text)   <-- over RAW bytes, NOT normalized/operative
```
**Strictly lossless.** No anatomy, no cleaned/pre-split text, no semantic-hierarchy assumptions, and — changed from the earlier draft — **no quality slot**: quality is now a versioned annotation (below), so a contamination detector can be upgraded without touching the source record. Storing Vaquill's own interpreted columns verbatim is **not** interpretation — we preserve what the dataset said, we do not re-derive it. The immutability/identity hash covers `raw_text` + source fields **only**.

### `DerivedArtifactProvenance` — shared by every annotation/artifact (multi-input DAG)
```
artifact_id        # = hash(sorted(input_ids), artifact_type, producer_name,
                   #        producer_version, config_hash)   — generated_at EXCLUDED
artifact_type
inputs[]:                # the DAG edges
    input_type     # source_record | assembly | annotation | oracle_edition
    input_id
producer_name         # a.k.a. parser_name
producer_version      # a.k.a. parser_version
config_hash           # a.k.a. parser_config_hash
generated_at       # audit metadata only; never in artifact_id
```
Every artifact anchors durable references to `source_record_id` (via an `inputs[]` edge of type `source_record`), **never** to `source_identity_key`. The **sorted-input-set** hash means two artifacts over different member sets never collide, and the DAG makes the recompute frontier on a new snapshot **computable** — recompute exactly the artifacts whose input set changed. A per-record annotation is simply the single-input case (`inputs = [that one source_record]`); a build-time oracle (USLM/eCFR edition) enters as an `oracle_edition` input, so `operative_text_hash`/`assembled_text_hash` honor the full-input reproducibility contract. Excluding `generated_at` from `artifact_id` keeps the id content-addressed (a byte-identical recompute yields the same id). `DocumentAnatomy`, `HierarchyTree`, `LegalChunk`, `ReferenceMention`, `LineageMention`, and `SourceDocumentAssembly` all follow this model rather than inventing their own.

### `SourceIdentityAnnotation` — versioned; groups/characterizes only, never composes (fed by M0.5A.1)
```
(DerivedArtifactProvenance)          # inputs = member source_record_ids
strategy_name          # usc_act_id_v1 | state_statute_act_id_v1 |
                       #   cfr_identity_v1 | federal_register_document_v1
source_identity_key
member_source_record_ids[]   # the candidate group; may be a single record
segment_fingerprint    # content-addressed; (act_id, raw_text_hash, occurrence_index)
segment_ordinal        # + segment_order_method, segment_order_confidence (snapshot_observed)
identity_scope         # record | provision | document | segment | numbering_bucket | unknown
identity_status        # resolved | ambiguous | provisional | unsupported
confidence
evidence[]
```
**Identity groups and characterizes; it does not compose.** Identity may conclude "R1/R2/R3 appear related, candidate = CFR §X" but must **not** decide "append R2 after R1" — that composition decision is `SourceDocumentAssembly`. Correct abstention is success; **100% identity coverage is not a metric**.
Note on `segment_fingerprint`: the only place ordering re-enters is `occurrence_index` disambiguating byte-identical duplicate rows. That is harmless — such rows carry `duplicate_row` and are semantically interchangeable, so the index is losslessness bookkeeping, never a semantic distinction.

### `DocumentClassificationAnnotation` — versioned
```
(DerivedArtifactProvenance)
document_class    # codified_cfr | federal_register | statute | regulation |
                 #   constitution | court_rule | guidance | unknown
authority_role   # operative_primary_law | promulgation_record | editorial_material |
                 #   guidance | unknown
confidence
```
Even where trivially deterministic (an `FR_*` prefix ⇒ Federal Register), it is our semantic interpretation of a source field. Keep it regenerable. The first producer is near-deterministic (`CFR_*` → `codified_cfr` / `operative_primary_law`; `FR_*` → `federal_register` / `promulgation_record`). **`corpus` is not sufficient to describe legal role** — `document_class`/`authority_role` are first-class, and downstream policy must not assume same-corpus ⇒ same retrieval semantics. **Test the retrieval-policy consequence now:** Federal Register defaults **OFF** for present-law / exact-CFR resolution (consistent with the M0.5A.1 finding that `FR_*` rows are co-numbered captures, not operative law).

### `QualityAnnotation` — versioned (first producer: `duplicate_row` only)
```
(DerivedArtifactProvenance)
quality_status    # unknown | clean | suspicious | rejected  (default unknown;
                 #   first producer emits only unknown / duplicate)
quality_flags[]   # duplicate_row (a cross-record conclusion, not a source assertion).
                 #   Later producers add: navigation/footer text, header repetition,
                 #   HTML remnants, encoding damage, suspiciously identical text across
                 #   many sections, missing legal markers
evidence[]
```
Quality is a cross-record conclusion, versioned by detector — kept **outside** the source record and its immutability hash. **Do not delete** suspicious rows — exclude from normal retrieval, preserve for investigation. (The withdrawn GA/NC statutes with leaked nav text are the cautionary tale; contamination enters at jurisdiction scale, so we need somewhere to represent it.)

**Scope-down (decision D):** the first `QualityAnnotation` producer is `duplicate_row` only, because assembly needs duplicate detection as an input and that is on the immediate path. The contamination detector (`clean` / `suspicious` / `rejected`, the GA/NC-boilerplate case) is **not** on the immediate path — nothing at risk is being assembled yet — so the interface exists now but that producer defers until a corpus at risk is ingested.

### `SourceDocumentAssembly` — versioned (composes an identity group into text)
```
(DerivedArtifactProvenance)          # inputs = member source_record_ids [+ oracle_edition if used]
source_identity_key                   # the group this assembles
member_source_record_ids[]
member_roles[]        # primary | continuation | duplicate | alternative | ambiguous
operations[]          # KEEP | APPEND | IGNORE_DUPLICATE | KEEP_SEPARATE | ABSTAIN
assembly_strategy     # cfr_source_assembly_v1 | trivial_single_record_v1 | ...
assembly_status       # complete | partial | ambiguous | noncomposable
assembled_text        # null when noncomposable / ambiguous
assembled_text_hash   # cross-snapshot change signal for multi-row sections
evidence[]
```
Assembly is the layer that *composes* member records of a `source_identity_key` group into a single document text — the decision identity is forbidden from making. It sits **between identity and anatomy**; anatomy validates a candidate assembly (one coherent operative structure ⇒ corroborate; N self-contained structures ⇒ reject), it never generates the assembly.

- One-row corpora (the 99% case) use `trivial_single_record_v1`: one member, `KEEP`, `assembly_status = complete`, `assembled_text = raw_text`. Assembly stays near-free for the common case.
- **`legal_id` attaches to the assembly, not the row** — this is the single attach point the assembly layer exists to provide (M0.5A.1 empirically disproved 1:1 source-to-document).
- The **plan/assembly split was cut** (decision A/D): operations, member roles, evidence, confidence, and status live as fields *on* `SourceDocumentAssembly`. There was no "validate the plan before materializing" step to hang a second artifact on — the anatomy validator runs on the materialized candidate text, not on a plan. If a human-in-the-loop approval workflow ever appears, re-splitting is trivial because the fields already exist.

### Durable-FK test (ships with `SourceIdentityAnnotation`)
Assert: identity strategy v1 (key A) and v2 (key B) coexist over the same records; downstream provenance referencing those records stays valid; no immutable artifact is keyed by `source_identity_key`. Extend the same coexistence test to assembly v1/v2 over the same members.

---

### Semantic-layer models (derived; after the annotation layer)

These consume the annotations above. They remain derived, versioned, and provenance-stamped.

#### CanonicalLegalDocument (derived, versioned)
```
# identity (per the orthogonal table; via the identified_as mapping)
legal_id
lineage_id            # optional; groups historically related provisions across moves
source_record_id[]    # the physical record(s) this document was assembled from
identity_status       # authoritative | stable_source | inferred | snapshot_local | ambiguous
identity_method       # e.g. open_us_law_source_id | cross_snapshot_renumbering_match
identity_confidence   # 0..1 (for inferred)
# legal metadata
corpus, jurisdiction, canonical_citation, citation_aliases[]
document_class, authority_role         # from DocumentClassificationAnnotation
hierarchy             # HierarchyNode[] (see below), verbatim + normalized
act_status, status_snapshot            # status is snapshot-qualified
# text views
operative_text        # anatomy-derived operative body
operative_text_hash   # = f(raw_text, anatomy_parser_version, [USLM_edition])
normalized_text, normalized_text_hash
# provenance: DerivedArtifactProvenance
```

#### DocumentAnatomy (derived)
Operative vs editorial/codification spans over `raw_text`. For USC, span labels are grounded in USLM concepts (`note`, `sourceCredit`, statutory/editorial/codification notes), not an invented taxonomy. Carries `DerivedArtifactProvenance`.

#### HierarchyNode (derived)
```
HierarchyNode(kind, identifier, label, source, confidence, ordinal)
# source ∈ {title_number, chapter, section_number, breadcrumb, display_path, uslm, ...}
```
Never a fixed federal `title/chapter/section` shape. Downstream code (esp. RELATIVE-reference resolution) stays agnostic to which evidence produced the node.

#### CitationAlias (temporal)
```
citation, legal_id, valid_from_snapshot, valid_to_snapshot
alias_type            # canonical | former | historical | alternate
```
Old addresses carry temporal metadata so an old cite is never silently resolved to a new provision without being marked historical.

#### ReferenceMention / CitationMention (pre-resolution)
```
reference_id, source_record_id, source_legal_id
raw_reference_text, start_char, end_char, structural_path
reference_type        # ABSOLUTE | QUALIFIED | LOCAL | RELATIVE | CONTAINER
parsed_jurisdiction, parsed_corpus, parsed_code,
parsed_title, parsed_chapter, parsed_section, parsed_subsection
parser_method         # e.g. usc_grammar_v1  (+ DerivedArtifactProvenance)
parser_confidence
```

#### ResolvedCitation (post-resolution)
```
reference_id
target_legal_id, target_source_record_id, target_lineage_id
resolution_method     # deterministic grammar | hierarchy | alias | lineage | model
resolution_confidence, candidate_targets[]
resolution_status     # resolved | ambiguous | unresolved | external | invalid
```
**Never force an ambiguous citation to resolve.** An explicit `unresolved`/`ambiguous` beats a confidently wrong edge. `external` (correctly out-of-corpus) is a **success**, kept distinct in metrics.

#### LineageMention (unresolved; derived from anatomy spans)
```
LineageMention
    source_record_id
    relationship_type          # renumbered_to | transferred_to | recodified_as | ...
    raw_target_reference       # e.g. "§ 321"
    structural/raw span
    extraction_method, extraction_confidence
    resolution_status = unresolved
```

#### CitationGraphEdge / LineageEdge (auditable)
```
CitationGraphEdge
    source_legal_id, source_record_id, target_legal_id, target_source_record_id
    raw_reference_text, reference_type, structural_path, start_char, end_char
    parser_method, resolver_method, parser_confidence, resolver_confidence
    snapshot_version
LineageEdge
    source_legal_id, target_legal_id
    relationship_type          # renumbered_to | transferred_to | recodified_as | predecessor_of | successor_of
    method, confidence, evidence[]
    snapshot_from, snapshot_to
```
A deterministic-grammar edge and an LLM-derived edge must never be indistinguishable in storage.

---

## Reproducibility contract

Every derived artifact is regenerable from:

> **the pinned snapshot-SET + producer name/version/config + any pinned external-oracle edition**

Three corrections to the naive "source record + parser version" model, learned in review:

1. **Cross-record inputs.** Resolution (corpus-wide alias index), lineage (both endpoints, often cross-snapshot), sibling ordering for RELATIVE references (needs the sibling set), and contamination-based quality (needs repetition across rows) are reproducible only from the snapshot-*set*. Consequence: retaining adjacent snapshots is a **correctness** dependency; and `resolution_status = external` is snapshot-corpus-scoped (a citation `resolved` while GA is present is `external` in v2026.08 after GA's withdrawal), so resolution is recomputed per snapshot, never cached across corpus-composition changes.
2. **External oracle.** If USC anatomy joins to USLM at runtime, `operative_text_hash = f(raw_text, anatomy_parser_version, USLM_edition)` — the oracle edition is a first-class input (or folded into the producer version). This must be decided (see M0.5B1).
3. **`operative_text_hash` is meaningless without `(anatomy_parser_name, anatomy_parser_version)`.** Comparison requires identical producer identity or an explicit controlled recompute.

---

## Anchoring rules (dual anchors)

Durable references use the anchor type that matches their purpose; keep both, and — per the durable-FK rule — anchor to physical/stable keys, never to `source_identity_key`.

- **Semantic/legal anchor** — `legal_id` (once established; else `source_record_id`) + `structural_path`. Survives reparsing; used by citation edges, lineage, relative-reference targets.
- **Exact provenance anchor** — `source_record_id` + raw `start/end` offsets + `raw_text_hash`, defined against immutable `raw_text`. Proves exactly which bytes a quote came from.

Anatomy reprocessing may change anatomy span IDs, chunk IDs, and offsets *within* operative text, but must **never** invalidate raw-source offsets, because those are defined against immutable `raw_text`.

---

## Resolution pipeline (deterministic-first)

```
raw section text
  → reference detection
  → reference classification (ABSOLUTE/QUALIFIED/LOCAL/RELATIVE/CONTAINER)
  → explicit citation grammar
  → hierarchy-aware resolver (LOCAL/RELATIVE/CONTAINER from this doc's HierarchyNode[])
  → citation alias index
  → lineage-aware resolver
  → model fallback  ← last resort only, for unresolved residuals
  → ResolvedCitation | AmbiguousCitation | UnresolvedCitation | External
```

Hierarchy-aware resolution **must abstain** (`ambiguous`) when hierarchy is incomplete, ordering is uncertain, or renumbering yields multiple plausible predecessors. Do not guess "the preceding section."

**Query-time exact lookup** is deterministic-first, not deterministic-only:
```
query → recognizer → normalizer → alias index → legal_id      (primary)
query → BM25 / sparse fallback                                (malformed/garbled cites)
query → dense retrieval                                       (natural-language questions, LATER)
```

---

## Chunking (parser owns structure; retrieval is downstream)

- One `CanonicalLegalDocument` → its chunks.
- Short section → one chunk. Do **not** split a section just to hit a token target.
- Oversized section → split on **structural markers** `(a)/(1)/(A)/(i)`, not arbitrary token windows.
- Every chunk keeps `structural_path` (primary, survives re-chunking) and raw `start/end` offsets (secondary, exact-quote verification, defined against immutable `raw_text`).
- Use the dataset's `subsection_count` as a **validation oracle**, not the splitter: parser count == dataset count → pass; mismatch → quality flag.

---

## Evaluation harness (four stages, no single "accuracy" number)

Report **precision AND recall**, broken down **by jurisdiction, corpus, reference type, parser method, and resolver method**. Aggregate accuracy is not acceptable — a parser can score 99% overall and be unusable for several small jurisdictions.

| Stage | Question | Metrics |
|---|---|---|
| A. Detection | Did we find that a reference exists? | precision, recall, F1 |
| B. Parsing | Did we extract jurisdiction/corpus/title/chapter/section/subsection correctly? | field accuracy, exact-parse accuracy |
| C. Resolution | Did the parsed cite map to the correct `legal_id`/document? | top-1 accuracy, Recall@K, ambiguity rate, unresolved rate |
| D. Version/Temporal | Correct snapshot/version/status for the question? | version-selection accuracy, status-selection accuracy |

Separate **`external` (correct out-of-corpus)** from **`unresolved` (resolver failed)** in Stage C, or the corpus's known holes (GA/NC withdrawn, regulations in a subset of jurisdictions) will masquerade as parser errors.

**Anatomy metrics are asymmetric** (false-stripping law ≫ leaving a note in): report operative-text **retention recall** first, then editorial-contamination rate, boundary exact-match rate, boundary-distance distribution, and unmatched-span counts on both sides.

**Oracle discipline:** validate USC against the **edition-pinned** USLM. Record the USLM edition/date. Do **not** compare v2026.08 against a newer official corpus and score legitimate amendments as parser errors; where exact alignment is impossible, measure and report the residual skew.

---

## Quality gate (ingestion, before indexing)

Assign `quality_status ∈ {unknown, clean, suspicious, rejected}` + `quality_flags[]` via the versioned `QualityAnnotation` (see Data contracts) — **not** on the source record. Candidate flags: navigation/footer text, header repetition, HTML remnants, abnormal boilerplate repetition, suspiciously identical text across many sections, encoding damage, missing expected legal markers. **Do not delete** suspicious rows — exclude from normal retrieval, preserve for investigation.

---

## Milestones (each ships with tests + acceptance criteria)

Sequencing is a DAG, not a straight line (see Sequencing below).

### M0 — Dataset reconnaissance *(COMPLETE)*
Full-snapshot schema/behavior report + `v2026.07→v2026.08` diff. See `reports/M0_recon.md`, `reports/M0_full_snapshot.md`, `reports/M0_act_id_stability.md`, and "What M0 established" above.

### M0.5A — Identity collision analysis *(COMPLETE)*
Enumerate every corpus with duplicate `act_id`. **Explanation before a key:** a composite key can make collisions technically unique while hiding a semantic bug, so distinguish (a) same `act_id` + different subsection rows, (b) `act_id` accidentally reused by upstream ETL, (c) `act_id` shared across related regulatory documents (e.g. CFR vs Federal Register sharing a namespace).
**Result** (`reports/M0.5A_identity_collisions.md`): collisions are entirely a regulations phenomenon (7 of 229 files; all statute/constitution `act_id`s unique). All three causes occur: (a) dominates `us_federal_regulations` `FR_*` — 165,044 of 165,067 `FR` collision groups are all-distinct-text (M0.5A read these as segmented documents; **M0.5A.1 corrected that** — they are co-numbered *distinct* documents, not ordered segments); (b) dominates state regs (Ohio 539/555 groups byte-identical) and the `CFR_*` residue (232 identical groups); (c) is the `CFR_*` vs `FR_*` namespace split coexisting in one file. Recommended strategy: `source_identity_key = (state, corpus, act_id, segment_ordinal)` for regulations (ordinal synthesized from row order — dataset has no per-segment discriminator; `section_number` is constant within an `FR` group), `legal_id = (state, corpus, act_id)` at document/section granularity, duplicate rows carry `quality_flags += duplicate_row` (kept for losslessness, collapsed at `legal_id`), and `document_class` tags `federal_register` vs `codified_cfr`. The recommendation is a **starting strategy**; M0.5A.1 hard-gates the frozen contract.

### M0.5A.1 — Collision-provenance + segment-order spike *(COMPLETE)*
Combined the collision-provenance and segment-order spikes into one experiment, **evidence-based, not an upstream-ETL trace**. Report at `reports/M0.5A1_segment_provenance.md`, built by `open_us_law_coverage.segment_provenance` (DuckDB `file_row_number` + memory-limited spill over the 11 GB federal `text` column).
**Result — two findings reshape M0.5A:**
1. **The cross-snapshot premise is empty.** Regulations — the only corpora where `act_id` collides — were *introduced* in v2026.08 (HF commit `2806c009c55c`); v2026.07 has **0 of 17** regulations files and none of the 7 colliding files. Exit questions 1, 2, and the "dataset-defined vs. snapshot-observed" half of 4 are therefore **untestable** and answered *evidence unavailable* — a standing correctness dependency to re-run when a second regulations-bearing snapshot ships, **not** a proven-stable result.
2. **`FR_*` distinct-text collisions are co-numbered distinct documents, not ordered segments** — correcting M0.5A's "one document split into ordered segments" reading. Evidence: their rows are physically **scattered** (essentially none form an adjacent block), the sampled **continuation rate is ≈0%** (no seam continues mid-sentence into the next row), and **≈96% of groups restart with the same agency preamble**. `CFR_*` is genuinely mixed (a minority of true continuations). So concatenating FR rows "in order" reconstructs nothing; they are alternative/self-contained captures under one Federal-Register number.

**Exit-question verdict:** (1,2) evidence unavailable; (3) no for `FR_*`, partly for `CFR_*`; (4) at best **snapshot-observed** — no structural column (`section_number`/`display_path`/`breadcrumb`/`citation`/`subsection_count`) varies within the vast majority of distinct groups, so no source-defined ordinal exists; (5) yes — emit `segment_ordinal` from physical row order (`segment_order_method = physical_row_order`, `segment_order_confidence = snapshot_observed`), `raw_text_hash` as content tiebreak, `duplicate_row` on byte-identical rows, collapse to `legal_id = (state, corpus, act_id)`, and treat FR full-text concatenation as **invalid** (not merely best-effort) since FR rows are co-numbered captures. Federal Register defaults OFF for operative-law resolution, which makes the unresolved segmentation tolerable.
This spike **hard-gated the source-identity contract** (it fixes the first `SourceIdentityAnnotation` strategy and the semantics of `segment_ordinal`) but not the immutable M1A core. **The contract may now freeze with the snapshot-observed-ordinal caveat.**

### M1A — `CanonicalSourceRecord` immutable core *(COMPLETE)*
Because the immutable core contains zero interpretation, it did not wait on A.1. Delivered in `src/open_us_law_coverage/source_record.py`: the frozen record model (`original_columns` as a read-only `MappingProxyType`), a schema-validating Parquet reader (`iter_source_records` streaming + row-group-bounded; `read_source_records` eager), snapshot metadata + source-file checksums (computed sha256, verified against `SHA256SUMS.json` in M0), insertion-preserving `physical_row_ordinal`, pure `compute_source_record_id` / `compute_raw_text_hash` functions, and verbatim 23-column preservation with `text` held once as `raw_text`. Deliberately boring.
**Exit (golden-fixture invariants) — all passing** (`uv run pytest`, 21 tests in `tests/test_source_record.py` over a hermetic multi-row-group synthetic fixture + the committed AK-constitutions sample): no text lost; every column preserved verbatim (null stays null, never invented); `source_record_id` deterministic from `(snapshot_version, source_file_checksum, physical_row_ordinal)` and independent of content; `raw_text[start:end]` resolves for stored offsets (incl. multibyte unicode); and the **boundary test** passes — a simulated "identity/anatomy/hierarchy/quality parser improved" (two producer generations emitting materially different annotations) requires **zero** changes to any `CanonicalSourceRecord`, and the records are immutable (mutation raises).
The annotation layer starts after its inputs exist: `SourceIdentityAnnotation` after A.1 (now unblocked); `DocumentClassificationAnnotation` and `QualityAnnotation` can begin immediately (their producers are versioned and regenerable regardless).

### M1A.5 — shared derived-artifact foundation
Build the shared derived-artifact contracts once, so every downstream annotation inherits provenance and the durable-FK discipline instead of re-inventing them. Deliverables:
- **`DerivedArtifactProvenance` as a multi-input DAG** (`artifact_id = hash(sorted(input_ids), artifact_type, producer_name, producer_version, config_hash)`, `generated_at` excluded; `inputs[]` are the DAG edges). The DAG makes the recompute frontier on a new snapshot computable.
- **`SourceIdentityAnnotation`** (groups/characterizes only, never composes) + the **durable-FK test** (identity strategy v1/v2 coexist over the same records; no immutable artifact keyed by `source_identity_key`; extended to assembly v1/v2).
- **`DocumentClassificationAnnotation`** — the near-deterministic first producer (`CFR_*` → codified_cfr/operative_primary_law; `FR_*` → federal_register/promulgation_record), and test the retrieval-policy consequence (FR default OFF for present-law/exact-CFR resolution).
- **`QualityAnnotation`** — first producer `duplicate_row` only (contamination detector deferred).
- **`SourceDocumentAssembly`** interface + the `trivial_single_record_v1` producer (one member, `KEEP`, `complete`, `assembled_text = raw_text`) so the 99% one-row case is covered immediately. `legal_id` attaches to the assembly, not the row.

**Exit:** the durable-FK coexistence test passes; the deterministic classification producer and the trivial-assembly producer run over the frozen M1A core; every artifact carries a well-formed provenance DAG; no durable FK anchors to `source_identity_key`.

### CFR-A1 — CFR assembly commissioning spike
Bounded (a deterministic sample, ~a few hundred groups — *not* a milestone). Cover the hard cases: byte-identical duplicates; obvious two-row continuations; >2-row groups; distinct co-numbered rows with no continuation; list/table boundaries; punctuation edge cases; partial/full variants. Validate the proposed assembly against **snapshot-aligned eCFR** (a build-time oracle).
**Metrics:** continuation-classification precision & recall; duplicate-classification precision; exact and normalized assembled-text match; ambiguous-group rate; **partial-law rate**; and — driving decision B — the **abstention rate on multi-row CFR groups**.
**Hard failure (zero tolerance):** an assembly marked `complete` whose text is missing operative provision text.

### CFR-A2 — `cfr_source_assembly_v1` producer + eligibility invariant
Pure **snapshot-internal** assembly (continuation signal + physical row order + dedup); anatomy validates the candidate (one coherent operative structure ⇒ corroborate; N self-contained structures ⇒ reject). When internal evidence is insufficient: `assembly_status = ambiguous`, and **do not concatenate**.
**Eligibility invariant:** a CFR section is returned as complete authority only if it is a proven single-record section **or** `assembly_status = complete`. Otherwise abstain or mark evidence incomplete (return `source_url`, not half a section). **Returning half a regulation under the whole-section citation is unacceptable.**

### M0.5B1 — USC anatomy (USLM-aligned)
**First step, before any metric:** decide USLM's role — *runtime join* (pin `USLM_edition` as a regeneration input / fold into producer version) vs *eval-only* (heuristic runtime detection, USLM measures it). This choice defines whether `operative_text_hash` honors the two-input contract and therefore what the spike measures. USLM is an **eval-only oracle** by default (the production parser runs from `raw_text` + parser version, preserving the two-input reproducibility contract). The experiment is **alignment, not heading-regex**: map USLM structured elements → expected flattened representation → align with Open US Law text → derive USLM-grounded span labels. Taxonomy follows USLM concepts (operative provision, source credit, editorial/statutory/codification notes, amendments, disposition, other).
**Exit — metrics split by consequence:**
- **HARD GATE** — `catastrophic_strip_count == 0` (no clearly-operative text omitted) and operative-text retention recall. A single catastrophic strip **blocks promotion** of that anatomy parser version.
- **QUALITY** — editorial-contamination rate into the operative body, alignment coverage, exact-boundary rate, unmatched OUL text, unmatched USLM material — on a USLM-aligned sample plus a manually-reviewed gold subset; `raw` vs `operative` change-rate measured across the v2026.07→v2026.08 transition.

### M0.5B2 — Hierarchy stress test
Run on CA statutes, TX statutes, and one 0%-flat-hierarchy regulation corpus. Output a normalized `HierarchyNode[]` (`kind`, `identifier`, `label`, `source`, `confidence`, `ordinal`), never a fixed federal `title/chapter/section` shape. LOCAL/RELATIVE/CONTAINER resolution operates only on the normalized tree.
**Exit — test topology, not just coverage** (LOCAL/RELATIVE/CONTAINER resolution depends on tree correctness, not label extraction): coverage; exact reconstruction where ground truth exists; abstention rate; **sibling ordering, parent uniqueness, acyclicity, and display-path round-trip**. Sibling-ordering consistency in particular is load-bearing — RELATIVE references depend on it.

**M0.5B2 — COMPLETE.** Report at `reports/M0.5B2_hierarchy.md`, built by `open_us_law_coverage.hierarchy` (breadcrumb JSON → normalized `HierarchyNode[]`, streaming the small structural columns only — never `text`). Ran on CA + TX statutes, **OH regulations** (the 0%-flat-title corpus, `agency/chapter/rule`), and **DE regulations** as a bonus stress case (`title/group/regulation` with unnumbered containers). Results:
- **The `HierarchyNode(kind, identifier, label, source, confidence, ordinal)` shape survives all four with zero interface changes** — `breadcrumb` parses 100%, and it carries variable-order CA codes, flat TX, and non-`title/chapter/section` regulation kinds without a corpus-specific field. Flat columns are confirmed unusable as the hierarchy source.
- **Topology tested, not just coverage:** acyclicity and proper-tree assembly (no multi-parent absolute node) are clean; display-path round-trips 100% (exact for statutes/OH; `label`-is-prefix for DE, where `display_path` appends node `name`).
- **Two load-bearing resolver findings:** (1) **bare-identifier LOCAL resolution is unsafe** — 12.4% (TX) to 25.6% (CA) of leaf `(kind,identifier)` keys appear under >1 parent (OH rule numbers are the exception at 0%), so resolution must key on the *absolute path*; (2) **sibling order is only partly recoverable from physical row order** (7.9% OH / 10.7% DE / 73.5% TX / 90.4% CA consistent with a natural sort of identifiers), so RELATIVE ("the preceding section") must **abstain** on the divergent remainder rather than guess.
- **Two clarifications recorded for the M1B freeze** (no type change): `identifier` is nullable and its absence is a first-class abstention (DE unnumbered `group`s → `identifier=None`, reduced confidence, never fabricated); and the **sibling ordinal is a tree-assembly product** with a per-corpus confidence, not a property of a single row. `HierarchyNode` gains a `DerivedArtifactProvenance` when promoted at M1B.

### M0.5B3 — CA abstraction probe
Not "run USC heuristics on CA" — parser rules are *expected* to be corpus-specific and their failure teaches little. Instead: take the artifact **output types** from B1/B2 (`DocumentAnatomy`, `AnatomySpan`, `HierarchyNode[]`, `StructuralPath`, `SourceDocumentAssembly`, `DerivedArtifactProvenance`) and test whether they represent a small CA sample **faithfully** (different anatomy categories, hierarchy node kinds, non-tree structures, article/part/division peculiarities, intermixed history, multiple breadcrumb conventions).
**Rule adopted — universal artifact model, corpus-specific producers:** *a parser implementation may be corpus-specific; the artifact interfaces must survive both USC and California.*
**Exit:** a list of type/interface changes CA forces (or confirmation none are needed) — captured **before** M1B freezes interfaces.

### M0.5C — Disposition extraction
Consume anatomy's codification/disposition spans (not raw text) → produce **unresolved** `LineageMention`s (`relationship_type`, `raw_target_reference`, span, `extraction_method`, `extraction_confidence`, `resolution_status = unresolved`). Stop at mentions — resolving the target citation needs the alias index (M3), so M0.5C must not build half the resolver.
**Exit:** extraction precision/recall on a hand-reviewed sample.

### M1B — Semantic freeze
With A.1, B1, B2, B3, C reported, freeze `CanonicalLegalDocument` and the derived-artifact interfaces. Freeze **lineage types** (`LineageEdge`, `LineageEvidence`, `relationship_type`, `resolution_status`) with **zero rows** permitted.
**Acceptance:** golden-fixture invariants for the derived layer; `legal_id`/`source_record_id`/`chunk_id` deterministic; every chunk maps to exactly one parent; character offsets resolve to correct text; missing metadata stays missing.

### M2 — USC citation detector + parser
Deterministically turn `42 U.S.C. § 1983` and its variants into structured `ReferenceMention`s. No embeddings.
**Acceptance:** Stage A + B metrics on a hand-labeled USC set meet baseline thresholds set after M0.5 (record the numbers; set targets, don't hardcode as "legal rules").

### M3 — USC resolver + alias index + USLM validation
Resolve citation → correct Open US Law row via canonical/alias lookup; build the exact-citation index; validate against edition-pinned USLM.
**Acceptance:** Stage C metrics (top-1, ambiguity, unresolved, external correctly separated) on the USLM-backed set; satisfies the First Success Criterion end-to-end with auditable explanations.

### M3.5 — Resolve `LineageMention` → `LineageEdge`
Disposition parsing becomes an early consumer/test of the resolver: resolve the extracted disposition targets into `LineageEdge`s.
**Acceptance:** lineage resolution precision/recall; evidence recorded per edge; no A/B merge on similarity alone.

### M4 — General in-body cross-reference parser + graph
Detect/resolve references inside section bodies; emit auditable `CitationGraphEdge`s (rule vs model distinguishable).
**Acceptance:** for a sample, "why does §A cite §B?" is answerable from stored edge fields; extraction vs resolution metrics reported separately.

### Later — CFR extension · State framework
Extend detection/parsing/resolution to federal regulations (`17 CFR 240.10b-5`), then jurisdiction-specific state grammars + alias tables (high-quality jurisdictions first), only after federal works end-to-end.
**Acceptance:** per-corpus / per-jurisdiction Stage A–C metrics at parity targets; abstain-rate tracked where hierarchy/ordering is weak.

---

## Sequencing

```
M0.5A.1  segment/collision-provenance spike  ── hard-gated identity contract   ── COMPLETE
   │
   ├── (parallel) M1A immutable CanonicalSourceRecord core                       ── COMPLETE
   │
source-identity contract FROZEN  (snapshot-observed-ordinal caveat, after A.1)
   │
M1A.5  DerivedArtifactProvenance(DAG) + SourceIdentityAnnotation
   │      + DocumentClassificationAnnotation + QualityAnnotation(duplicate-only)
   │      + SourceDocumentAssembly(trivial_single_record_v1) + durable-FK test
   │
   ├── CFR path:  identity groups CFR collisions → CFR-A1 commissioning (eCFR oracle)
   │              → CFR-A2 cfr_source_assembly_v1  (eligibility invariant gates CFR retrieval)
   │
   └── (parallel) M0.5B1 anatomy · M0.5B2 hierarchy · M0.5B3 CA probe
   │
M0.5C  disposition → unresolved LineageMention
   │
M1B  freeze semantic derived-artifact interfaces  (freeze lineage types with zero rows)
   │
M2 detector/parser → M3 resolver/alias index → M3.5 resolve LineageMention → M4 in-body refs
   │
Later: CFR resolution (consumes assembled CFR text) · State framework
```

**Gate semantics (precise):** M0.5A.1 gated the *source-identity contract*, not raw ingestion; that contract is now frozen. The lossless M1A record serializer did not need to know how `legal_id` works. In M1A.5 the artifact *interfaces* co-land (they are independent), but the *producers* are ordered **identity-then-assembly**: the assembly producer composes over a `source_identity_key` group, so it runs after `SourceIdentityAnnotation` has grouped the CFR collision members (decision C). B and C need not block M1A.5; C must not start before B yields a trustworthy codification/disposition span. Do **not** freeze M1B until B1/B2/B3 and CFR-A1/A2 have reported.

---

## Design decisions (M1A.5 / CFR / M0.5B review)

A skeptical pass on the accreted design produced one cut, one scope-down, and four stated decisions. The assembly layer itself is load-bearing and stays: M0.5A.1 empirically disproved 1:1 source-to-document, `legal_id` needs a single attach point, the multi-input provenance DAG is an ugly retrofit if deferred, and the trivial one-row pass-through keeps assembly near-free for the 99% case.

**A. `SourceAssemblyPlan` vs `SourceDocumentAssembly` — collapsed into one.** We had split assembly into a *plan* (the KEEP/APPEND/IGNORE_DUPLICATE/… decision) and an *assembly* (the materialized text), on the theory the plan could be reviewed before materialization. That doesn't survive contact with the workflow: the anatomy validator runs on the **materialized candidate text**, not on a plan — there is no "validate the plan before materializing" step to hang a second artifact on. Operations, evidence, confidence, and status live as fields *on* `SourceDocumentAssembly`. Re-split later only if a human approval step appears; the fields already exist.

**B. eCFR build-time-fallback trigger — default to pure snapshot-internal with abstention.** Only reconsider the eCFR-pinned build-time fallback if CFR-A1 abstains on **>50% of multi-row CFR groups**, and even then improve the internal heuristic first. Multi-row CFR is ~1,083 groups (~0.5% of ~220k CFR provisions), and abstention is a *safe* outcome (returns `source_url`, never partial law), so recovering a fraction of a fraction does not justify a build-time external dependency until the heuristic is demonstrably not working.

**C. Identity vs assembly sequencing — interfaces co-land, producers are ordered.** The assembly *interface* lands in M1A.5 alongside identity (interfaces are independent). The assembly *producer* runs after `SourceIdentityAnnotation` has grouped the CFR collision members, since it composes over a `source_identity_key` group.

**D. Over-engineering cut / deferred.** Cut the separate `SourceAssemblyPlan` (per A). Scoped `QualityAnnotation`'s first producer to `duplicate_row` only and deferred the contamination detector: assembly needs duplicate detection now; nothing at risk is being assembled yet, so the contamination producer defers until a corpus at risk is ingested.

---

## Cross-cutting invariants

- **Anatomy-as-derived holds only under three conditions:** (1) identity depends on nothing anatomy produces; (2) change-detection pins `(snapshot_version, anatomy_parser_version)` as a pair; (3) durable references anchor to source-level keys (the semantic and provenance anchors above; the durable-FK rule), never to anatomy-derived artifacts or to `source_identity_key`.
- **Snapshot retention is a correctness dependency.** Retain adjacent Open US Law snapshots used for identity/amendment/lineage (`v2026.07`, `v2026.08` are the first fixtures). Over time, measure across multiple transitions: `P(act_id stable | ordinary amendment, corpus)`, `P(identity changed | renumbering, corpus)`, `P(raw_text changes | operative body unchanged)`. One transition is commissioning evidence, not a permanent guarantee.
- **`cross_references_usc` is not yet a silver label.** The field-present rate is **not** a recall floor — true citation density is unknown. Before M4, build a small stratified hand-labeled citation set (rows with the field; rows with empty field but citation-shaped text; no-reference rows; long sections; operative-body vs editorial-note references; unusual forms) and independently measure dataset-field precision/recall and parser precision/recall. **"Parser finds a valid citation, field is empty" must never auto-count as a false positive.**
- **Status is snapshot-qualified.** Emit "in force as represented in Open US Law v2026.08," never "currently in force."
- **Standing regression (register now).** On every new Open US Law snapshot (v2026.09+ first), rerun the collision/segment/order suite; the provenance DAG defines the exact recompute frontier (recompute only the artifacts whose input set changed). This is the first chance to test FR-group, CFR-collision, row-order, and identity-strategy stability — several M0.5A.1 exit questions are *evidence unavailable* until a second regulations-bearing snapshot ships. Do not rely on humans remembering why the next snapshot matters.

---

## Snapshot-diff (for future releases)

Version comparison at the **document** level (not chunk IDs). Pipeline: source-identity match → `legal_id` match → raw-text hash → operative-text hash → citation/hierarchy comparison → status-transition analysis → similarity/lineage inference → classify as `unchanged | amended | added | removed | renumbered | transferred | recodified | status_changed | possible_successor | ambiguous`. Only changed/new documents get re-processed. (M0 delivered the `act_id`-stability diff; `snapshot_diff.py` is the seed of this pipeline.)

---

## MVP scope recap

Lossless immutable source store · versioned identity/classification/quality annotations · derived canonical legal document (anatomy + hierarchy) · USC detection/parsing/normalization/exact resolution · citation alias index · lineage mentions → edges · USC/CFR cross-references where feasible · deterministic hierarchy-aware local resolution · structural subsection parsing with paths + offsets · whole-section default chunking with structural overflow · parser/resolver metrics · USLM validation.

---

## Guardrails

- Status is snapshot-qualified: emit "in force as represented in Open US Law v2026.08," never "currently in force."
- The LLM never constructs citations or source URLs from memory; application code assigns citation IDs; deterministic post-hoc validation checks every emitted citation exists, was actually provided, and quoted text is present in the cited source.
- This is not legal advice; official source should be checked before reliance.

---

## Terminology (defer, don't churn)

Reserve **"canonical"** for the immutable source representation. `CanonicalLegalDocument` (the semantic object) may later be renamed (`ParsedLegalDocument` / `NormalizedLegalDocument` / `LegalDocumentView`). The intent is noted now; **do not rename during M0.5**.

---

## First action for Claude Code

1. ~~Run **M0.5A.1**~~ **DONE** — `reports/M0.5A1_segment_provenance.md`. The source-identity contract froze with the *snapshot-observed ordinal* caveat (cross-snapshot stability untestable until a second regulations snapshot; `FR_*` rows are co-numbered distinct captures, so no reading order / no valid concatenation).
2. ~~Build the **M1A immutable core** with the boundary test in its acceptance suite~~ **DONE** — `src/open_us_law_coverage/source_record.py` + `tests/test_source_record.py` (`uv run pytest`, boundary test green).
3. Do **not** anchor any durable artifact FK to `source_identity_key`.
4. **Now: build M1A.5** — the `DerivedArtifactProvenance` multi-input DAG and the durable-FK test; ship the `trivial_single_record_v1` assembly producer and the deterministic `DocumentClassificationAnnotation` producer; scope `QualityAnnotation` to `duplicate_row`. `SourceIdentityAnnotation` (fed by A.1) is built on the frozen M1A core; assembly interfaces co-land with it, but the assembly *producer* runs after identity groups the members.
5. **Run CFR-A1** against snapshot-aligned eCFR (human-staged, edition-pinned); report the metrics, especially the multi-row-CFR **abstention rate** (drives decision B).
6. **In parallel, start M0.5B1 / B2 / B3** (decide USLM runtime-vs-eval first for B1; respect the B→C dependency).

Do not freeze `CanonicalLegalDocument` (M1B) until B1, B2, B3, and CFR-A1/A2 have also reported. The one hard rule: keep `source_record_id`, `raw_text_hash`, and `legal_id` orthogonal — `legal_id` derives from proven source identity alone, corrected additively, and durable FKs anchor to `source_record_id`, never to `source_identity_key`.
