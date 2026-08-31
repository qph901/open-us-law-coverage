# Project priorities

These priorities govern roadmap and optimization decisions. A lower priority must
not be improved by making a higher priority materially worse.

## 1. Law coverage

The primary objective is broad, measurable, date-pinned coverage of applicable
law. File counts and row counts describe inventory; they are not coverage
percentages.

Coverage must be reported separately by jurisdiction, corpus, and legal-content
cutoff using official sources as the denominator. At minimum, measure:

- expected official provisions and provisions represented;
- missing, stale, duplicate, ambiguous, and unexpected provisions;
- exact and normalized text agreement;
- citation-resolution success, ambiguity, and unresolved rates; and
- provenance for the official edition used as the comparison oracle.

The current snapshot inventory is documented in
[`reports/M0_full_snapshot.md`](reports/M0_full_snapshot.md). A defensible coverage
percentage requires provision-level comparison with pinned official inventories,
including USLM/GovInfo for USC and point-in-time eCFR for CFR.

## 2. Retrieval time

The secondary objective is fast retrieval of the correct, covered law. Report
latency separately for exact-citation lookup and broader search, including:

- p50, p95, and p99 latency;
- cold-start and warm-query latency;
- index-build time and index size; and
- the hardware, corpus size, and cache state used for the measurement.

A latency result qualifies only when the correct provision is returned. Faster
retrieval does not compensate for missing, stale, ambiguous, or incorrect law.

## Engineering guardrails

Automated tests, code coverage, linting, typing, reproducible reports, and CI are
reliability controls. They support the priorities above but are not primary
measures of project success.
