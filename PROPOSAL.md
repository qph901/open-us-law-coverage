# Proposal: Citation Parser & Resolver for Open US Law (parser-first, USC-commissioned)

## Summary

Build a **citation detection / parsing / normalization / resolution** subsystem over the `vaquill/open-us-law` dataset (snapshot **v2026.08**), commissioned on the US Code (USC) and validated against edition-pinned USLM XML. This is the **hard foundation** of a legal RAG system. Retrieval and generation come *after* we can reliably identify what law a citation refers to, with an auditable explanation.

The guiding rule for the whole system: **uncertainty about legal identity must be represented as data, never hidden inside ID-generation code.** The system must be able to say "these are the same provision," "strong evidence this was renumbered into that," or "cannot reliably establish continuity" — and keep those as materially different claims.

The architecture that serves that rule is a **source/interpretation split**:

- **CanonicalSourceRecord** — what the dataset told us. Lossless, immutable, almost no legal interpretation.
- **CanonicalLegalDocument** — what our parsers *believe* the legal structure means. Derived, versioned, improvable.
- **LegalChunk / CitationEdge / LineageEdge / DocumentAnatomy / HierarchyNode** — derived artifacts, each carrying its own provenance.

This gives uncertainty an explicit home and lets parsers improve without ever rewriting provenance.

**Status:** M0 (dataset reconnaissance) is **complete** — see `reports/M0_recon.md`, `reports/M0_full_snapshot.md`, and `reports/M0_act_id_stability.md`. The current phase is the **M0.5 commissioning spikes → M1 (source/interpretation split)** described below. This document is the single source of truth; it carries the design decisions converged during review and supersedes any earlier sequencing.

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

**Additional non-goals for the current (M0.5→M1) phase:** no embeddings/vector DB/reranker; no general state citation grammars; no full CA/state coverage (only a small CA commissioning sample runs end-to-end); no *resolved* lineage before M3; no official-source URL recovery.

---

## Prerequisites (human actions — an agent cannot do these)

1. **Accept the dataset terms.** `vaquill/open-us-law` is gated on Hugging Face; a human must accept conditions and provide an HF access token to the environment.
2. **Pin the snapshot(s).** Confirm the exact snapshot in use (target: `v2026.08`) and record it. Retain the adjacent snapshot (`v2026.07`) — snapshot retention is a **correctness** dependency, not eval convenience (see Cross-cutting invariants).
3. **Provide the USLM oracle.** Download OLRC USLM XML for the USC, **edition-pinned to the release at or before the snapshot's content date** (OLRC keys USC releases to public-law numbers). Record the exact USLM edition/date used.
4. **Confirm network access** for the agent's environment to Hugging Face and govinfo.gov (or stage the files locally).
5. **Point at the existing codebase** if this extends prior marker-class parsing work; adapt conventions accordingly rather than starting greenfield.

---

## What M0 established (recon findings that anchor the design)

M0 loaded the real v2026.08 Parquet (full 229-file / 2,978,617-row snapshot) and diffed `v2026.07 → v2026.08`. The findings below replace the earlier "assumptions to test" — the production design is grounded in these, not in the dataset card.

- **Uniform 24-column schema across all 229 files.** One normalizer handles every corpus and jurisdiction.
- **No predecessor/successor crosswalk column exists anywhere.** Lineage across renumber/transfer/recodify must be **inferred**, not read from a field. The only lineage-adjacent signals are `act_status`, `cross_references_usc/cfr`, `public_laws_referenced`, and disposition prose in the text.
- **`act_id` is a normalized, namespaced citation** (`USC_T42_C21_S1983`, `STATE_AK_…`, `SCONST_AK_…`). It is 100% populated in every corpus and is a good stable-source seed — **but it is NOT unique within the federal regulations file** (a genuine collision). Bare `act_id` semantics are therefore not universal; identity must go through a corpus-specific strategy (drives M0.5A).
- **`act_id` is stable across the v2026.07→v2026.08 transition**: no `act_id` was ever removed or reissued, and thousands survive text amendment → viable Tier-1 identity seed. **Caveat:** the USC `text` field bundles a volatile editorial-notes apparatus, so `text_hash` over raw `text` overstates real amendment (~48% of USC rows "changed," almost all editorial-note growth). The operative body must be hashed separately — this directly motivates the anatomy work (M0.5B1) and the identity correction below.
- **Flat hierarchy columns are not reliable across jurisdictions.** California leaves `title_number` null on ~70% of rows (it namespaces by *code*, e.g. `Cal. BPC`); the real hierarchy lives in `breadcrumb` / `display_path`. USC and AK flat columns are ~100% clean.
- **USC cross-references ship pre-extracted** (`cross_references_usc` as `"title:section"` arrays), dense on federal USC and sparse elsewhere, plus `public_laws_referenced`. A head start and an oracle for M4 — but **field-present rate is not a recall floor** (see Cross-cutting invariants).
- **Disposition often lives in the text.** ~10,395 rows carry a disposition status; many `renumbered` rows state their successor inline (`[§2010. Renumbered §321]`), giving a deterministic lineage edge; `transferred`/`omitted` history sits in `Editorial Notes / Codification` prose and needs a dedicated parser.

---

## Identity model (four orthogonal concepts)

**Decision adopted this round:** `legal_id` must **not** derive from `raw_text_hash`, citation text, or any content/interpretation. M0 proved USC `raw_text` changes when editorial apparatus changes even though the provision does not; binding identity to content recreates that churn. Keep four concerns orthogonal:

| Concept | Question it answers | Derived from |
|---|---|---|
| `source_id` | what the dataset called it | corpus-specific source identity (e.g. `act_id` + required namespace) |
| `legal_id` | which legal object? | `source_id` **only**, where stability is proven; else snapshot-local |
| `document_id` (a.k.a. `version_id`) | which snapshot representation? | `namespace(snapshot_version, legal_id-or-source_id)` |
| `raw_text_hash` | which exact bytes? | `hash(raw_text)` |

`raw_text_hash` is deliberately **not** inside `document_id`: a harmless upstream reformat should yield the *same* document address with a *different* fingerprint, not a new identity. **Never** compute `legal_id = hash(canonical_citation)`; citation stays a resolvable alias/address, not identity.

### Stability tiers (how `legal_id` is assigned)

- **Proven stable source** — where M0/M0.5 prove `source_id` is populated, unique in its namespace, and fixed under text-only amendment, seed `legal_id = namespace(source_id)`. `stability_class = proven`.
- **Snapshot-local** — a row with no trustworthy stable identifier does **not** manufacture identity from its citation. Emit a deterministic snapshot-local `document_id`; `stability_class = snapshot_local`. Represent the gap honestly.
- **Cross-snapshot lineage (inferred)** — for `renumbered` / `transferred` / `recodified` rows, where `source_id` is expected to break, infer lineage from multiple signals (high-similarity operative-text hash, hierarchy match, section-number transition, status flag, neighbor continuity, explicit disposition language). Record a `LineageEdge` with method/confidence/evidence. **Do not merge** A and B into one `legal_id` on similarity alone; link via `lineage_id`, keep distinct `legal_id`s.
- **USC bonus:** cross-check `source_id` continuity against the USLM `@identifier`; divergence flags a likely renumbering and doubles as free lineage evidence and resolver validation.

### Source identity is corpus-specific

The federal-regulation `act_id` collision proves bare `act_id` is not a universal key. Identity resolution goes through a versioned strategy, never a hardcoded key:

```
SourceIdentityStrategy          # one per corpus, versioned
    identity_key(record)      -> source_id
    namespace(record)         -> namespace tuple
    stability_class(record)   -> proven | snapshot_local | unknown
    confidence(record)
```

No shared base class or DB schema may assume `act_id` alone is a key. USC may return `(jurisdiction, corpus, act_id)`; CFR may require an additional discriminator determined by M0.5A. Note `jurisdiction` is uniformly `"US"`; `state` is the real discriminator.

---

## Reproducibility contract

Every derived artifact is regenerable from:

> **the pinned snapshot-SET + parser name/version/config + any pinned external-oracle edition**

Three corrections to the naive "source record + parser version" model, learned in review:

1. **Cross-record inputs.** Resolution (corpus-wide alias index), lineage (both endpoints, often cross-snapshot), sibling ordering for RELATIVE references (needs the sibling set), and contamination-based quality (needs repetition across rows) are reproducible only from the snapshot-*set*. Consequence: retaining adjacent snapshots is a **correctness** dependency; and `resolution_status = external` is snapshot-corpus-scoped (a citation `resolved` while GA is present is `external` in v2026.08 after GA's withdrawal), so resolution is recomputed per snapshot, never cached across corpus-composition changes.
2. **External oracle.** If USC anatomy joins to USLM at runtime, `operative_text_hash = f(raw_text, anatomy_parser_version, USLM_edition)` — the oracle edition is a first-class input (or folded into the parser version). This must be decided (see M0.5B1).
3. **`operative_text_hash` is meaningless without `(anatomy_parser_name, anatomy_parser_version)`.** Comparison requires identical parser identity or an explicit controlled recompute.

Every derived artifact therefore carries one provenance model rather than inventing its own:

```
DerivedArtifactProvenance
    source_document_id
    parser_name
    parser_version
    parser_config_hash
    oracle_edition        # nullable; e.g. USLM edition when used at runtime
    generated_at
```

`DocumentAnatomy`, `StructuralTree`, `LegalChunk`, `ReferenceMention`, `LineageMention` all follow this model.

---

## Anchoring rules (dual anchors)

Durable references use the anchor type that matches their purpose; keep both.

- **Semantic/legal anchor** — `document_id` + `structural_path`. Survives reparsing; used by citation edges, lineage, relative-reference targets.
- **Exact provenance anchor** — `document_id` + raw `start/end` offsets + `raw_text_hash`, defined against immutable `raw_text`. Proves exactly which bytes a quote came from.

Anatomy reprocessing may change anatomy span IDs, chunk IDs, and offsets *within* operative text, but must **never** invalidate raw-source offsets, because those are defined against immutable `raw_text`.

---

## Architecture

Canonical **source** store is the immutable ground truth; the canonical **legal document** and all indexes are derived and regenerable. Rebuilding a derived layer (new anatomy parser, new chunker, new embedding model) must have **zero** effect on `source_id` / `legal_id` / `document_id`.

```
Open US Law snapshot-set (Parquet, gated)            + USLM oracle (edition-pinned)
        │
   Lossless Serializer + Quality-flag slot
        │
   CanonicalSourceRecord   ← immutable ground truth (raw_text, source fields, provenance)
        │
   ┌──────────── DERIVED (versioned, regenerable, provenance-stamped) ────────────┐
   │  DocumentAnatomy (operative vs editorial spans; USLM-aligned for USC)         │
   │  HierarchyNode[] + StructuralTree   → CanonicalLegalDocument                  │
   │  LegalChunk                                                                   │
   │  Reference Detector → Classifier → Citation Grammar                           │
   │  Hierarchy-aware Resolver → Alias Index → Lineage-aware Resolver              │
   │  LineageMention → LineageEdge   ·   CitationEdge (auditable; rule vs model)   │
   └──────────────────────────────────────────────────────────────────────────────┘
        │
   Retrieval Indexes (exact-citation index first; BM25/dense LATER)
        │
   RAG (LATER)
```

---

## Core data models

Concrete field lists; adapt names to the existing codebase. The split is the point: `CanonicalSourceRecord` is lossless and immutable; everything else is derived and carries `DerivedArtifactProvenance`.

### CanonicalSourceRecord (lossless, immutable)
```
snapshot_version
source_file
# identity (verbatim; interpreted only via a SourceIdentityStrategy)
source_id                 # corpus-specific source identity, exactly as supplied
# all 24 original schema fields, verbatim
act_id, citation, citation_short, state, jurisdiction, document_type,
title_number, title_name, chapter, chapter_name, section_number, section_title,
breadcrumb, display_path, act_status, text, word_count, source_url,
last_amended_year, subsection_count, cross_references_usc, cross_references_cfr,
public_laws_referenced, year
# text + fingerprint
raw_text                  # = text, immutable
raw_text_hash             # = hash(raw_text)   <-- over RAW bytes, NOT normalized/operative
# quality (the ONE explicitly-mutable annotation)
quality_status            # unknown | clean | suspicious | rejected  (default unknown)
quality_flags[]
```
**Strictly lossless.** No anatomy, no cleaned/pre-split text, no semantic-hierarchy assumptions. The immutability/identity hash covers `raw_text` + source fields **only**; `quality_status`/`quality_flags` are **excluded** from it and versioned by detector — so a contamination detector can be upgraded without churning provenance. (The GA/NC withdrawal proves contamination enters at jurisdiction scale; we need somewhere to represent it.)

### CanonicalLegalDocument (derived, versioned)
```
# identity (from source, per the orthogonal table above)
source_id
legal_id
lineage_id            # optional; groups historically related provisions across moves
document_id           # this provision in THIS snapshot
identity_status       # authoritative | stable_source | inferred | snapshot_local | ambiguous
identity_method       # e.g. open_us_law_source_id | cross_snapshot_renumbering_match
identity_confidence   # 0..1 (for inferred)
# legal metadata
corpus, jurisdiction, canonical_citation, citation_aliases[]
hierarchy             # HierarchyNode[] (see below), verbatim + normalized
act_status, status_snapshot   # status is snapshot-qualified
# text views
operative_text        # anatomy-derived operative body
operative_text_hash   # = f(raw_text, anatomy_parser_version, [USLM_edition])
normalized_text, normalized_text_hash
# provenance: DerivedArtifactProvenance
```

### DocumentAnatomy (derived)
Operative vs editorial/codification spans over `raw_text`. For USC, span labels are grounded in USLM concepts (`note`, `sourceCredit`, statutory/editorial/codification notes), not an invented taxonomy. Carries `DerivedArtifactProvenance`.

### HierarchyNode (derived)
```
HierarchyNode(kind, identifier, label, source, confidence)
# source ∈ {title_number, chapter, section_number, breadcrumb, display_path, uslm, ...}
```
Downstream code (esp. RELATIVE-reference resolution) stays agnostic to which evidence produced the node.

### CitationAlias (temporal)
```
citation, legal_id, valid_from_snapshot, valid_to_snapshot
alias_type            # canonical | former | historical | alternate
```
Old addresses carry temporal metadata so an old cite is never silently resolved to a new provision without being marked historical.

### ReferenceMention (pre-resolution)
```
reference_id, source_document_id, source_legal_id
raw_reference_text, start_char, end_char, structural_path
reference_type        # ABSOLUTE | QUALIFIED | LOCAL | RELATIVE | CONTAINER
parsed_jurisdiction, parsed_corpus, parsed_code,
parsed_title, parsed_chapter, parsed_section, parsed_subsection
parser_method         # e.g. usc_grammar_v1  (+ DerivedArtifactProvenance)
parser_confidence
```

### ResolvedCitation (post-resolution)
```
reference_id
target_legal_id, target_document_id, target_lineage_id
resolution_method     # deterministic grammar | hierarchy | alias | lineage | model
resolution_confidence, candidate_targets[]
resolution_status     # resolved | ambiguous | unresolved | external | invalid
```
**Never force an ambiguous citation to resolve.** An explicit `unresolved`/`ambiguous` beats a confidently wrong edge. `external` (correctly out-of-corpus) is a **success**, kept distinct in metrics.

### LineageMention (unresolved; derived from anatomy spans)
```
LineageMention
    source_document_id
    relationship_type          # renumbered_to | transferred_to | recodified_as | ...
    raw_target_reference       # e.g. "§ 321"
    structural/raw span
    extraction_method, extraction_confidence
    resolution_status = unresolved
```

### CitationGraphEdge / LineageEdge (auditable)
```
CitationGraphEdge
    source_legal_id, source_document_id, target_legal_id, target_document_id
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

- One source record → one `CanonicalLegalDocument`.
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

Assign `quality_status ∈ {unknown, clean, suspicious, rejected}` + `quality_flags[]`, stored on the source record **outside** the immutability hash (see CanonicalSourceRecord). Candidate flags: navigation/footer text, header repetition, HTML remnants, abnormal boilerplate repetition, suspiciously identical text across many sections, encoding damage, missing expected legal markers. **Do not delete** suspicious rows — exclude from normal retrieval, preserve for investigation. (The withdrawn GA/NC statutes with leaked nav text are the cautionary tale.)

---

## Milestones (each ships with tests + acceptance criteria)

Sequencing is a DAG, not a straight line:

```
M0.5A  Identity collision analysis ──┐ (gates identity contract only)
                                      │
M1A  Lossless CanonicalSourceRecord  ◄┘  (storage mechanics may start immediately;
                                          identity contract freezes after A)
        │  in parallel (calendar time):
        ├── M0.5B1  USC anatomy (USLM-aligned)   ──┐ (B→C internal dependency)
        ├── M0.5B2  Hierarchy stress test (CA/TX/hard regulation corpus)
        ├── M0.5B3  CA abstraction probe (do the artifact TYPES survive CA?)
        └── M0.5C   Disposition extraction (consumes anatomy spans → LineageMention)
        ▼
M1B  Freeze CanonicalLegalDocument + derived-artifact interfaces
        ▼
M2 USC detector/parser → M3 resolver → M3.5 resolve disposition into lineage edges → M4 general in-body refs
        ▼
Later: CFR extension · State framework
```

**Gate semantics (precise):** M0.5A gates the *source-identity contract*, not raw ingestion. The lossless record serializer can start immediately because it need not know how `legal_id` works. B and C need not block M1A; C must not start before B yields a trustworthy codification/disposition span.

### M0 — Dataset reconnaissance *(COMPLETE)*
Full-snapshot schema/behavior report + `v2026.07→v2026.08` diff. See `reports/M0_recon.md`, `reports/M0_full_snapshot.md`, `reports/M0_act_id_stability.md`, and "What M0 established" above.

### M0.5A — Identity collision analysis
Enumerate every corpus with duplicate `act_id` (federal regulations first). **Explanation before a key:** a composite key can make collisions technically unique while hiding a semantic bug, so distinguish (a) same `act_id` + different subsection rows, (b) `act_id` accidentally reused by upstream ETL, (c) `act_id` shared across related regulatory documents (e.g. CFR vs Federal Register sharing a namespace). Report per collision group: `row count | distinguishing columns | text relationship | hierarchy relationship | source_url relationship | hypothesized cause | recommended identity policy`.
**Exit:** each collision class explained by phenomenon; a recommended per-corpus `SourceIdentityStrategy`. Then freeze the source-identity contract.

### M1A — Lossless CanonicalSourceRecord
Strictly-lossless serializer per the data model above: `snapshot_version`, `source_file`, all original fields verbatim, `raw_text`, `raw_text_hash`, source-identity fields, and the `quality_status`/`quality_flags` slot. No anatomy, no cleaned/pre-split text, no semantic-hierarchy assumptions.
**Exit (golden-fixture invariants):** no text lost; `source_id`/`legal_id`/`document_id` deterministic and orthogonal per the identity table; `raw_text[start:end]` resolves for stored offsets; null source fields stay null (never invented); `quality_status` outside the immutability hash; snapshot + status survive ingestion.

### M0.5B1 — USC anatomy (USLM-aligned)
**First step, before any metric:** decide USLM's role — *runtime join* (pin `USLM_edition` as a regeneration input / fold into parser version) vs *eval-only* (heuristic runtime detection, USLM measures it). This choice defines whether `operative_text_hash` honors the two-input contract and therefore what the spike measures. The experiment is **alignment, not heading-regex**: map USLM structured elements → expected flattened representation → align with Open US Law text → derive USLM-grounded span labels.
**Exit:** the asymmetric anatomy metrics (see Evaluation) measured on a USLM-aligned sample plus a manually-reviewed gold subset; `raw` vs `operative` change-rate measured across the v2026.07→v2026.08 transition.

### M0.5B2 — Hierarchy stress test
Run on CA statutes, TX statutes, and one 0%-flat-hierarchy regulation corpus. Output is a normalized `HierarchyNode[]` (not a "breadcrumb parser"), so downstream code stays agnostic to which evidence produced each node.
**Exit:** coverage; exact reconstruction where ground truth exists; abstention rate; sibling-ordering consistency (RELATIVE references depend on it).

### M0.5B3 — CA abstraction probe
Not "run USC heuristics on CA" — parser rules are *expected* to be corpus-specific and their failure teaches little. Instead: take the artifact **output types** from B1/B2 (`DocumentAnatomy`, `HierarchyNode[]`, `StructuralPath`, `DerivedArtifactProvenance`) and test whether they can represent a small CA sample **faithfully** (different anatomy categories, hierarchy node kinds, non-tree structures, article/part/division peculiarities, intermixed history, multiple breadcrumb conventions).
**Rule adopted:** *a parser implementation may be corpus-specific; the artifact interfaces must survive both USC and California.*
**Exit:** a list of type/interface changes CA forces (or confirmation none are needed) — captured **before** M1B freezes interfaces.

### M0.5C — Disposition extraction
Consume anatomy's codification/disposition spans (not raw text) → produce **unresolved** `LineageMention`s. Stop at mentions — resolving the target citation needs the alias index (M3), so M0.5C must not build half the resolver.
**Exit:** extraction precision/recall on a hand-reviewed sample.

### M1B — Semantic freeze
With A, B1, B2, B3, C reported, freeze `CanonicalLegalDocument` and the derived-artifact interfaces. Freeze **lineage types** (`LineageEdge`, `LineageEvidence`, `relationship_type`, `resolution_status`) with **zero rows** permitted.
**Acceptance:** golden-fixture invariants for the derived layer; `legal_id`/`document_id`/`chunk_id` deterministic; every chunk maps to exactly one parent; character offsets resolve to correct text; missing metadata stays missing.

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

## Cross-cutting invariants

- **Anatomy-as-derived holds only under three conditions:** (1) identity depends on nothing anatomy produces; (2) change-detection pins `(snapshot_version, anatomy_parser_version)` as a pair; (3) durable references anchor to source-level keys (semantic and provenance anchors above), never to anatomy-derived artifacts.
- **Snapshot retention is a correctness dependency.** Retain adjacent Open US Law snapshots used for identity/amendment/lineage (`v2026.07`, `v2026.08` are the first fixtures). Over time, measure across multiple transitions: `P(act_id stable | ordinary amendment, corpus)`, `P(identity changed | renumbering, corpus)`, `P(raw_text changes | operative body unchanged)`. One transition is commissioning evidence, not a permanent guarantee.
- **`cross_references_usc` is not yet a silver label.** The field-present rate is **not** a recall floor — true citation density is unknown. Before M4, build a small stratified hand-labeled citation set (rows with the field; rows with empty field but citation-shaped text; no-reference rows; long sections; operative-body vs editorial-note references; unusual forms) and independently measure dataset-field precision/recall and parser precision/recall. **"Parser finds a valid citation, field is empty" must never auto-count as a false positive.**
- **Status is snapshot-qualified.** Emit "in force as represented in Open US Law v2026.08," never "currently in force."

---

## Snapshot-diff (for future releases)

Version comparison at the **document** level (not chunk IDs). Pipeline: `source_id` match → `legal_id` match → raw-text hash → operative-text hash → citation/hierarchy comparison → status-transition analysis → similarity/lineage inference → classify as `unchanged | amended | added | removed | renumbered | transferred | recodified | status_changed | possible_successor | ambiguous`. Only changed/new documents get re-processed. (M0 delivered the `act_id`-stability diff; `snapshot_diff.py` is the seed of this pipeline.)

---

## MVP scope recap

Lossless source store (identity + provenance + quality slot) · derived canonical legal document (anatomy + hierarchy) · USC detection/parsing/normalization/exact resolution · citation alias index · lineage mentions → edges · USC/CFR cross-references where feasible · deterministic hierarchy-aware local resolution · structural subsection parsing with paths + offsets · whole-section default chunking with structural overflow · parser/resolver metrics · USLM validation.

---

## Guardrails

- Status is snapshot-qualified: emit "in force as represented in Open US Law v2026.08," never "currently in force."
- The LLM never constructs citations or source URLs from memory; application code assigns citation IDs; deterministic post-hoc validation checks every emitted citation exists, was actually provided, and quoted text is present in the cited source.
- This is not legal advice; official source should be checked before reliance.

---

## First action for Claude Code

1. **M0.5A** — identity collision analysis with the report format above (explanation before a key); recommend per-corpus `SourceIdentityStrategy`.
2. In parallel, **start the M1A lossless serializer** (storage mechanics only; do not freeze the identity contract until A returns).
3. **M0.5B1** — begin by deciding USLM runtime-vs-eval, then run the USLM-alignment anatomy experiment with the asymmetric metrics.
4. **M0.5B2 / B3 / C** follow per the DAG (B→C dependency respected).

Do not freeze `CanonicalLegalDocument` (M1B) until A, B1, B2, B3, and C have reported. The one hard rule: keep `legal_id`, `document_id`, and `raw_text_hash` orthogonal — `legal_id` derives from proven source identity alone.
