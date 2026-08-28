# NEXT — the agreed next move

**Date:** 2026-08-28 · **Snapshot:** v2026.08 · **Status of this document:** the settled,
actionable build plan. Six review documents now exist (`GPT_REVIEW_1..3`,
`CLAUDE_REVIEW_1..3`) and have converged; this file supersedes their back-and-forth and
resolves the four residual deltas. It is written to be executed, not debated further.

---

## The one next milestone

> **M1A.5 closure — identity contracts, concrete producers, and artifact integrity.**
> Close the derived-layer contracts, then build the concrete `SourceIdentityStrategy`
> producers on the corrected contracts, then recommission the evidence. **No CFR assembly
> and no M1B semantic freeze until this is done.**

Rationale (uncontested across all six reviews): concrete identity is the only substantial
critical-path feature that needs neither the USLM nor the eCFR oracle; the derived shapes
have not yet persisted any artifacts, so correcting them now is a design edit, but the
moment the first concrete producer emits them they become migration problems. Close first,
build second.

---

## Resolved decisions (the four residual deltas)

Each was a live difference between `CLAUDE_REVIEW_3.md` and `GPT_REVIEW_3.md`. Settled here.

**D1 — Multi-member identity uses an explicit, content-addressed group. (Adopt GPT_REVIEW_3 #1.)**
My earlier shorthand — "one annotation per segment sharing a `source_identity_key`" — is
withdrawn: read literally it groups members through a *mutable* key with no group artifact,
which reintroduces the exact incomplete-recompute-frontier bug that `DuplicateScope` was
built to fix (add/remove a sibling and the existing per-member conclusions do not re-hash).
The faithful `DuplicateScope` analogue is a group artifact plus per-member annotations, and
that is what we build (shapes in Phase A.1).

**D2 — `artifact_id` stays a derivation address; a new `payload_hash` field carries the
semantic content address. (Synthesis — neither "fold it in" nor "leave it alone.")**
GPT is right that the collision is reachable by ordinary release-discipline failure (a
deterministic producer's code changes without a version bump, or an output-affecting knob
is not folded into `config_hash`), not only by hand-construction — so the body *must* be
addressable. I was right that folding the body hash into `artifact_id` destroys the
pre-computable derivation address the DAG recompute-frontier relies on. Both concerns are
satisfied by **not making one id do two jobs** — which is exactly the project's own M1A
precedent: `source_record_id` (physical/derivation) is already kept orthogonal to
`raw_text_hash` (content). Apply that same house rule to the derived layer:

- `artifact_id` — unchanged; the derivation address, pre-computable from
  `(type, inputs, producer, version, config)`.
- `payload_hash` — **new field on every derived artifact**; the canonical hash of the
  semantic body (all conclusion fields, audit metadata excluded), validated in
  `__post_init__` against the body.
- **Tripwire invariant:** any store or test that ever observes two artifacts with equal
  `artifact_id` and unequal `payload_hash` raises — that is precisely the "unbumped
  producer change" GPT describes, now surfaced as an error instead of a silent overwrite.

The advertised guarantee is corrected to: *equal `artifact_id` ⇒ equal
`(inputs, producer, version, config)`; equal `payload_hash` ⇒ equal canonical semantic
payload (audit metadata excluded); a well-governed store never holds two payloads under one
`artifact_id`.*

**D3 — Contracts are frozen before any producer is written. (Adopt GPT_REVIEW_3 #3.)**
My "let the 1:1 producers run in parallel with Phase A" exemption is withdrawn, because D1
restructures the identity shape itself: even a 1:1 producer emits a single-member
`SourceIdentityGroup` + one member annotation, so it is downstream of the shape decision.
Writing it against today's scalar-segment `SourceIdentityAnnotation` and rewriting it after
would churn code and certify the wrong intermediate contract. The 1:1 path is still the
*first producer implemented*; it is not the *first task*.

**D4 — The snapshot pin is established by checksum-matching, never by transcribing a commit
prefix. (Adopt GPT_REVIEW_3 #4.)**
My suggestion to paste `2806c009c55c…` from the M0.5A.1 report into `SNAPSHOT_REVISIONS` is
withdrawn: that commit *introduced* regulations but is not proof it is the exact revision
every staged local Parquet came from — later commits could change bytes under the same
label. The correct procedure is in Phase C.1.

---

## Phase A — correct and freeze the contracts

No producer work begins until Phase A lands with tests.

**A.1 — Explicit identity group + per-member annotation.** In
`src/open_us_law_coverage/derived/identity.py`, replace the multi-member-but-scalar-segment
`SourceIdentityAnnotation` with the `DuplicateScope`-analogue pair:

```
SourceIdentityGroup            # content-addressed by the COMPLETE member set
  provenance                   #   artifact_type = source_identity_group;
                               #   inputs = sorted source_record edges of every member
  strategy_name                #   usc_act_id_v1 | state_statute_act_id_v1 |
                               #     cfr_identity_v1 | federal_register_document_v1 | ...
  source_identity_key
  member_source_record_ids     #   the complete candidate group (sorted, unique)
  identity_scope               #   record | provision | document | segment | ...
  identity_status              #   resolved | ambiguous | provisional | unsupported
  confidence
  payload_hash                 #   D2
  evidence[]

SourceIdentityMemberAnnotation # one per member (mirrors per-member QualityAnnotation)
  provenance                   #   inputs = [SourceIdentityGroup artifact, this source_record]
  target_source_record_id      #   the one member this annotation is about
  segment_fingerprint          #   bound to THIS member — no longer a lone scalar on the group
  segment_ordinal              #   snapshot-observed physical row order (M0.5A.1)
  segment_order_method         #   physical_row_order | single_record | unknown
  segment_order_confidence     #   snapshot_observed | source_defined | not_applicable
  payload_hash                 #   D2
  evidence[]
```

Add `SOURCE_IDENTITY_GROUP` to `ArtifactType`. A single-member group (the 1:1 case) is the
degenerate instance: one member, `single_record`, `not_applicable`. The scalar segment
fields never again sit unbound on a multi-member object.

**A.2 — `payload_hash` on every derived artifact (D2).** Add a pure
`compute_payload_hash(...)` per artifact type in `provenance.py` (canonical serialization of
the conclusion fields, `generated_at` and any audit-only field excluded), a `payload_hash`
field on every derived dataclass, and its `__post_init__` check. Add the equal-id/unequal-payload
tripwire as a reusable assertion and a test. Correct the "byte-identical serialized object"
wording in `provenance.py` and `CLAUDE.md` to the D2 guarantee.

**A.3 — Uniform construction-time validation (the GPT_REVIEW_1/2 #4 finding).** Give every
derived model a `__post_init__` that enforces, at minimum: the provenance `artifact_type`
matches the model; declared members/targets agree with the provenance `source_record`
edges; `confidence ∈ [0,1]`; strategy/identity/producer keys are non-empty; and `payload_hash`
is consistent (A.2). Today only `Evidence`, `DerivedArtifactProvenance`, and
`SourceDocumentAssembly` validate; extend to `SourceIdentityGroup`,
`SourceIdentityMemberAnnotation`, `DocumentClassificationAnnotation`, `DuplicateScope`,
`QualityAnnotation`, and `AssemblyIdentityAssociation`.

**A.4 — Assembly membership is exact, not set-based.** In `assembly.py`, replace
`set(members) != set(edges)` with a check that rejects duplicate members and requires exact
canonical (sorted, unique) agreement with the provenance source-record inputs.

**A.5 — Producer versions are constants, not caller-controlled.** Remove the
`producer_version=...` override from the production functions (`assemble_trivial_single_record`,
`classify_source_record`, and the new identity producers). Replace the synthetic assembly
v1/v2 coexistence test with a real legacy fixture (a stored v1-shaped artifact) or an
explicit incompatibility test, so the durable-FK property is exercised against a genuine
shape difference rather than two labels of one body.

**Phase A exit:** all six derived models reject malformed direct construction; the
equal-id/unequal-payload tripwire test passes; the assembly member check rejects duplicates;
no production function accepts a version override; existing 130 tests still green.

---

## Phase B — implement the concrete identity producers (on the frozen contracts)

**B.1 — The 1:1 strategies first (the low-risk commissioning step).** `usc_act_id_v1`,
`state_statute_act_id_v1`, and a constitution strategy, each emitting a single-member
`SourceIdentityGroup` + one `SourceIdentityMemberAnnotation`, keyed `(state, corpus, act_id)`,
`identity_status = resolved`, `single_record` / `not_applicable`. This is the first point at
which `CanonicalSourceRecord → identity → trivial assembly` runs end-to-end over a real
corpus; assert the full chain composes a real statute record with `assembled_text ==
raw_text`, byte-for-byte.

**B.2 — The regulations collision strategies.** `cfr_identity_v1` and
`federal_register_document_v1` over `us_federal_regulations`, emitting **multi-member**
`SourceIdentityGroup`s with one `SourceIdentityMemberAnnotation` per row. Preserve the frozen
M0.5A.1 semantics without exception: `segment_ordinal` is snapshot-observed physical row
order and never a reading order; FR rows are never concatenated; `duplicate_row` runs only
within the group; ambiguity abstains. These groups are the input CFR-A2 will consume.

**B.3 — Graduate the durable-FK tests.** Move the durable-FK and v1/v2 coexistence tests
from fabricated annotations to **actual producer outputs**: identity strategy v1/v2 coexist
over the same records; no artifact keyed by `source_identity_key`; a membership change
re-hashes the group and every affected member annotation (the recompute frontier is complete).

**Phase B exit:** the 1:1 and regulations producers run row-group-bounded over the staged
samples (skipping cleanly when absent); the durable-FK suite passes against real outputs.

---

## Phase C — recommission and pin the evidence

**C.1 — Establish the snapshot pin by checksum (D4).** Resolve candidate dataset history to
full commit SHAs; for each candidate, compare its `SHA256SUMS.json` against the sha256 of the
staged local Parquet files (the streamed checksum `download.py` already computes). The
revision whose manifest matches every staged file becomes `SNAPSHOT_REVISIONS["v2026.08"]`,
and its `DOWNLOAD_METADATA.json` is written. If **no** revision matches all staged files,
record that limitation explicitly rather than assert a false pin, and re-download from a
deliberately chosen immutable revision. Also make `verify()` treat a requested file absent
from `SHA256SUMS.json` as a failure (today it prints `??` and continues), and write
`DOWNLOAD_METADATA.json` only after every checksum passes.

**C.2 — Re-run the CA probe with the real producers.** Update `ca_probe.py` to actually
construct `SourceIdentityGroup` / `SourceIdentityMemberAnnotation` and run
`detect_duplicate_rows` within each group, and either run the trivial assembler over the full
corpus or label the 200-row check as sampled. Narrow the B3 report wording from "runs every
built producer over it" to what it executes.

**C.3 — Deterministic full-snapshot identity manifest.** A new byte-stable report over the
full snapshot with per-corpus group-size distribution, collision counts, within-group
duplicate counts, ambiguity, and abstention rate — the first end-to-end evidence that the
identity layer behaves at scale, and the natural regression fixture for the next snapshot.

**C.4 — Reconcile the docs.** Fix the `trivial_single_record_v1` → `v2` drift (`README.md:74`,
`PROPOSAL.md:496/530/573/648`), update the M1A.5 status in `README.md`/`PROPOSAL.md`/`CLAUDE.md`
to reflect the closed contracts and built producers, and record the corrected `artifact_id`
guarantee (D2) and the identity group/member shape (D1).

**C.5 — Stage the human oracles in parallel (non-blocking).** Surface, but do not gate
Phases A–C on: edition-pinned USLM (M0.5B1), edition-pinned eCFR (CFR-A1), and retention of a
second regulations-bearing snapshot v2026.09+ (M0.5A.1's evidence-unavailable exit questions).

---

## Exit criteria for M1A.5 closure

- Equal `artifact_id` ⇒ equal `(inputs, producer, version, config)`; equal `payload_hash` ⇒
  equal canonical semantic payload; a store never holds two payloads under one `artifact_id`.
- Every segment fingerprint and ordinal is bound to exactly one source record; changing any
  group member re-hashes the group artifact and every affected per-member conclusion.
- All derived types reject malformed direct construction; assembly rejects duplicate members.
- Production callers cannot relabel producer versions; the v1/v2 durable-FK test runs against
  a genuine shape difference.
- The concrete 1:1 and regulations identity producers exist and the durable-FK suite passes
  against **real** producer outputs.
- The corrected CA probe and the full-snapshot identity manifest reproduce byte-for-byte.
- The local v2026.08 evidence is tied by checksum to a recorded full immutable revision, or
  its provenance limitation is stated explicitly.
- All existing tests plus the new adversarial contract tests pass.

## After this milestone

CFR-A1 commissioning against human-staged edition-pinned eCFR → CFR-A2 (`cfr_source_assembly_v1`)
decision rules **from the commissioned thresholds** (safety scaffolding — the eligibility
invariant, abstention, sampling harness — may be built earlier; decision rules may not) →
M0.5B1/B2/B3 and CFR gates all reported → **M1B** semantic freeze. Do not freeze M1B before
those gates.

---

## First concrete task

Start at **A.1 + A.2**: introduce `SourceIdentityGroup` / `SourceIdentityMemberAnnotation`
and the `payload_hash` field with its tripwire, with a new `tests/test_identity_group.py` and
the `payload_hash` cases folded into `tests/test_derived_provenance.py`. Everything else in
Phase A slots in behind those two, and no producer is written until Phase A is green.
