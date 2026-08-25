# Proposal: Citation Parser & Resolver for Open US Law (parser-first, USC-commissioned)

## Summary

Build a **citation detection / parsing / normalization / resolution** subsystem over the `vaquill/open-us-law` dataset (snapshot **v2026.08**), commissioned on the US Code (USC) and validated against edition-pinned USLM XML. This is the **hard foundation** of a legal RAG system. Retrieval and generation come *after* we can reliably identify what law a citation refers to, with an auditable explanation.

The guiding rule for the whole system: **uncertainty about legal identity must be represented as data, never hidden inside ID-generation code.** The system must be able to say "these are the same provision," "strong evidence this was renumbered into that," or "cannot reliably establish continuity" — and keep those as materially different claims.

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

---

## Prerequisites (human actions — an agent cannot do these)

1. **Accept the dataset terms.** `vaquill/open-us-law` is gated on Hugging Face; a human must accept conditions and provide an HF access token to the environment.
2. **Pin the snapshot.** Confirm the exact snapshot in use (target: `v2026.08`) and record it; a later snapshot will contain different text for the same statute.
3. **Provide the USLM oracle.** Download OLRC USLM XML for the USC, **edition-pinned to the release at or before the snapshot's content date** (OLRC keys USC releases to public-law numbers). Record the exact USLM edition/date used.
4. **Confirm network access** for the agent's environment to Hugging Face and govinfo.gov (or stage the files locally).
5. **Point at the existing codebase** if this extends prior marker-class parsing work; adapt conventions accordingly rather than starting greenfield.

---

## Verified facts vs assumptions to test

**Verified (from Vaquill's own API docs):**
- The dataset carries a provider stable ID, `act_id` (a.k.a. `actId`), formatted like `USC_T42_C21_S1983`. Guidance is to take it from data, never hand-build it.
- **Critical implication:** that format is a *normalized citation* — the title/chapter/section is baked into the ID. Therefore `act_id` is **stable under ordinary text amendment** (number unchanged) but **structurally cannot be stable across renumbering / transfer / recodification** (the number in the ID changes). It does not, by itself, solve cross-move identity.
- Vaquill points to the **USLM `@identifier` attribute** as the stable federal key precisely because tree position shifts on renumbering. Use it as a second, independent identity signal for USC.

**Assumptions Milestone 0 must confirm against real Parquet (do not design final identity rules until these are answered):**
- Is `act_id` populated for every corpus and unique within `(jurisdiction, corpus)`?
- Does `act_id` stay fixed under text-only amendment across two snapshots?
- Does `act_id` change under `renumbered` / `transferred` / `recodified` statuses? (Expected: yes → those rows route to lineage inference.)
- Does the schema contain **any** predecessor/successor crosswalk field (`formerly_cited_as`, `renumbered_from`, etc.)? (Card does **not** advertise one; confirm.)
- Are hierarchy and sibling-ordering clean enough to resolve `LOCAL` / `RELATIVE` / `CONTAINER` references deterministically, or is the abstain path the common case?
- How variable is citation format per jurisdiction?

---

## Architecture

Canonical store is the source of truth. Retrieval indexes are disposable derived artifacts — rebuilding them (new chunker, new embedding model) must have **zero** effect on `legal_id` / `document_id`.

```
Open US Law snapshot (Parquet, gated)
        │
   Dataset Normalizer + Quality Gate
        │
   Canonical Legal Store   ← source of truth (text, identity, version, provenance)
        │
 ┌──────────────── PARSER / RESOLVER (this project) ────────────────┐
 │  Structural Parser                                               │
 │  Reference Detector → Reference Classifier → Citation Grammar     │
 │  Hierarchy-aware Resolver → Alias Index → Lineage-aware Resolver  │
 │  (model fallback = last resort)                                   │
 │  Citation Graph Builder (auditable edges)                         │
 └──────────────────────────────────────────────────────────────────┘
        │
   Retrieval Indexes (exact-citation index first; BM25/dense LATER)
        │
   RAG (LATER)
```

---

## Core data models

Concrete field lists; adapt names to the existing codebase.

### CanonicalLegalDocument
```
# identity
source_id            # Vaquill act_id, verbatim from data
legal_id             # our canonical provision identity (seeded from act_id; see Identity Model)
lineage_id           # optional; groups historically related provisions across moves
document_id          # this provision in THIS snapshot

identity_status      # authoritative | stable_source | inferred | snapshot_local | ambiguous
identity_method      # e.g. open_us_law_act_id | cross_snapshot_renumbering_match
identity_confidence  # 0..1 (for inferred)

# version / provenance
snapshot_version
source_file
source_url           # provenance only; may be null; null != "no identity"

# legal metadata
corpus
jurisdiction
canonical_citation
citation_aliases[]   # see CitationAlias
hierarchy            # title/chapter/etc., verbatim + normalized
act_status           # verbatim from snapshot
status_snapshot      # = snapshot_version (status is snapshot-qualified, not timeless)

# text
raw_text             # immutable
text_hash            # = hash(raw_text)   <-- NOT over normalized_text
normalized_text
normalized_text_hash # = hash(normalized_text)

# quality
quality_status       # clean | suspicious | rejected
quality_flags[]
```

### CitationAlias (temporal)
```
citation
legal_id
valid_from_snapshot
valid_to_snapshot
alias_type           # canonical | former | historical | alternate
```
Old addresses must carry temporal metadata so an old cite is never silently resolved to a new provision without being marked historical.

### ReferenceMention (pre-resolution)
```
reference_id
source_document_id
source_legal_id
raw_reference_text
start_char, end_char, structural_path
reference_type       # ABSOLUTE | QUALIFIED | LOCAL | RELATIVE | CONTAINER
parsed_jurisdiction, parsed_corpus, parsed_code,
parsed_title, parsed_chapter, parsed_section, parsed_subsection
parser_method        # e.g. usc_grammar_v1
parser_confidence
```

### ResolvedCitation (post-resolution)
```
reference_id
target_legal_id, target_document_id, target_lineage_id
resolution_method    # deterministic grammar | hierarchy | alias | lineage | model
resolution_confidence
candidate_targets[]
resolution_status    # resolved | ambiguous | unresolved | external | invalid
```
**Never force an ambiguous citation to resolve.** An explicit `unresolved`/`ambiguous` beats a confidently wrong edge. `external` (correctly out-of-corpus) is a **success**, not a failure — keep it distinct in metrics.

### CitationGraphEdge (auditable)
```
source_legal_id, source_document_id
target_legal_id, target_document_id
raw_reference_text, reference_type, structural_path, start_char, end_char
parser_method, resolver_method
parser_confidence, resolver_confidence
snapshot_version
```
A deterministic grammar edge and an LLM-derived edge must never be indistinguishable in storage.

### LineageEdge
```
source_legal_id, target_legal_id
relationship_type    # renumbered_to | transferred_to | recodified_as | predecessor_of | successor_of
method, confidence, evidence[]
snapshot_from, snapshot_to
```

---

## Identity model (tiered, evidence-based)

- **Tier 1 — stable source identity.** If M0 proves `act_id` is populated, unique in namespace, and fixed under text-only amendment, seed `legal_id = namespace(jurisdiction, corpus, act_id)`. Do **not** fold `citation`, `raw_text_hash`, or `snapshot_version` into `legal_id`. Set `identity_status = stable_source`.
- **Tier 2 — snapshot-local.** If a row has no trustworthy stable identifier, do **not** manufacture identity from its citation. Emit a deterministic snapshot-local `document_id` and set `identity_status = snapshot_local`. Represent the gap honestly.
- **Tier 3 — cross-snapshot lineage inference.** For `renumbered` / `transferred` / `recodified` rows — where `act_id` is expected to break — infer lineage from multiple signals (identical/high-similarity text hash, hierarchy match, section-number transition, status flag, neighboring-section continuity, explicit predecessor language). Record a `LineageEdge` with method/confidence/evidence. **Do not merge** A and B into one `legal_id` on similarity alone; link them via `lineage_id` and keep distinct `legal_id`s. Set `identity_status = inferred`.
- **Never** `legal_id = hash(canonical_citation)`. Citation stays a resolvable alias/address, not identity.
- **USC bonus:** cross-check `act_id` continuity against the USLM `@identifier`; divergence flags a likely renumbering and doubles as free lineage evidence and resolver validation.

---

## Resolution pipeline (deterministic-first)

```
raw section text
  → reference detection
  → reference classification (ABSOLUTE/QUALIFIED/LOCAL/RELATIVE/CONTAINER)
  → explicit citation grammar
  → hierarchy-aware resolver (LOCAL/RELATIVE/CONTAINER from this doc's structure)
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

- One Parquet row → one `CanonicalLegalDocument`.
- Short section → one chunk. Do **not** split a section just to hit a token target.
- Oversized section → split on **structural markers** `(a)/(1)/(A)/(i)`, not arbitrary token windows.
- Every chunk keeps `structural_path` (primary, survives re-chunking) and `start_char/end_char` (secondary, for exact-quote verification).
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

**Oracle discipline:** validate USC against the **edition-pinned** USLM. Record the USLM edition/date. Do **not** compare v2026.08 against a newer official corpus and score legitimate amendments as parser errors; where exact alignment is impossible, measure and report the residual skew.

---

## Quality gate (ingestion, before indexing)

Assign `quality_status ∈ {clean, suspicious, rejected}` + `quality_flags[]`. Candidate flags: navigation/footer text, header repetition, HTML remnants, abnormal boilerplate repetition, suspiciously identical text across many sections, encoding damage, missing expected legal markers. **Do not delete** suspicious rows — exclude from normal retrieval, preserve for investigation. (The withdrawn GA/NC statutes with leaked nav text are the cautionary tale.)

---

## Milestones (each ships with tests + acceptance criteria)

### M0 — Dataset reconnaissance *(do this first; blocks final identity design)*
Load real v2026.08 Parquet across all major corpora. Produce a schema report: field names/types, null rates, `act_id` behavior (the four assumption checks above), status distribution, citation-format samples per jurisdiction, hierarchy/ordering cleanliness, text-length distribution, cross-reference coverage.
**Acceptance:** written report answering every assumption in "Verified facts vs assumptions." No production parser is designed from the dataset card alone.

### M1 — Canonical document store
Ingest → `CanonicalLegalDocument` with identity (per tiered model informed by M0), `raw_text` hashing, snapshot provenance, `act_status` + `status_snapshot`, quality gate.
**Acceptance (golden-fixture invariants):** no legal text lost; `legal_id`/`document_id`/`chunk_id` deterministic; every chunk maps to exactly one parent; character offsets resolve to correct text; missing metadata stays missing (never invented); `source_url=null` distinct from a guessed URL; snapshot + status survive ingestion.

### M2 — USC citation detector + parser
Deterministically turn `42 U.S.C. § 1983` and its variants into structured `ReferenceMention`s. No embeddings.
**Acceptance:** Stage A + B metrics on a hand-labeled USC set meet baseline thresholds set after M0 (record the numbers; set targets, don't hardcode as "legal rules").

### M3 — USC citation resolver + alias index + USLM validation
Resolve citation → correct Open US Law row via canonical/alias lookup; build the exact-citation index; validate against edition-pinned USLM.
**Acceptance:** Stage C metrics (top-1, ambiguity, unresolved, external correctly separated) on the USLM-backed set; satisfies the First Success Criterion end-to-end with auditable explanations.

### M4 — USC in-body cross-reference parser + graph
Detect/resolve references inside section bodies; emit auditable `CitationGraphEdge`s (rule vs model distinguishable).
**Acceptance:** for a sample, "why does §A cite §B?" is answerable from stored edge fields; extraction vs resolution metrics reported separately.

### M5 — Structural parser
Parse section/subsection/paragraph/subparagraph/clause; store `structural_path` + offsets; split only oversized sections.
**Acceptance:** structural reconstruction test (ordered chunks rebuild source text); `subsection_count` cross-check passes or flags.

### M6 — CFR
Extend detection/parsing/resolution to federal regulations (`17 CFR 240.10b-5` forms).
**Acceptance:** Stage A–C metrics for CFR at parity targets.

### M7 — State framework
Introduce jurisdiction-specific grammars + alias tables; prioritize high-quality jurisdictions first. Only after federal works end-to-end.
**Acceptance:** per-jurisdiction Stage A–C metrics; abstain-rate tracked where hierarchy/ordering is weak.

---

## Snapshot-diff (for future releases)
Version comparison at the **document** level (not chunk IDs). Pipeline: `source_id` match → `legal_id` match → raw-text hash → citation/hierarchy comparison → status-transition analysis → similarity/lineage inference → classify as `unchanged | amended | added | removed | renumbered | transferred | recodified | status_changed | possible_successor | ambiguous`. Only changed/new documents get re-processed.

## MVP scope recap
Canonical store (identity + provenance + quality gate) · USC detection/parsing/normalization/exact resolution · citation alias index · USC/CFR cross-references where feasible · deterministic hierarchy-aware local resolution · structural subsection parsing with paths + offsets · whole-section default chunking with structural overflow · parser/resolver metrics · USLM validation.

## Guardrails
- Status is snapshot-qualified: emit "in force as represented in Open US Law v2026.08," never "currently in force."
- The LLM never constructs citations or source URLs from memory; application code assigns citation IDs; deterministic post-hoc validation checks every emitted citation exists, was actually provided, and quoted text is present in the cited source.
- This is not legal advice; official source should be checked before reliance.

---

## First action for Claude Code
Confirm prerequisites are in place, then execute **M0** and return the reconnaissance report. Do not design the final `legal_id` rule or write parser grammars until M0 answers the `act_id` behavior questions — the tiered identity model branches on those results.

