# Oracle and legal-content currency registry

[`v2026.08.json`](v2026.08.json) is the machine-validated currency record for the
two oracle-relevant federal corpora. The statute cutoff is established as
2025-01-06 from the snapshot's uniform `USCODE-2024` GovInfo provenance and the
official edition metadata. The regulations cutoff remains unresolved because the
file mixes 220,018 CFR rows from three source years with 362,036 historical Federal
Register rows. The dataset repository's 2026-08-26 commit is only a publication
date and is never substituted for either corpus's legal-content date.

The registry also gives stable `oracle_edition` identifiers and immutable
point-in-time/release-point candidates. Their `local_path` and `sha256` remain null
until the source bytes are staged and compared with the snapshot. A null checksum is
therefore visible unfinished work, never an implicit claim that a moving "current"
oracle was used.

Oracle pin exit criteria:

1. Download the complete candidate edition into `data/oracles/` without changing
   the source bytes.
2. Record its repository-relative path and SHA-256 in the registry.
3. Compare the relevant Open US Law corpus with that edition to confirm an
   upstream-metadata cutoff or document residual skew.
4. Change `cutoff_status` to `established` only with authoritative upstream
   metadata or comparison evidence, and use the registry's `oracle_edition` as an
   `oracle_edition` provenance edge in every consuming derived artifact.

The aligned USLM candidate is the OLRC release point through Public Law 118-274
dated 2025-01-06, except Public Law 118-159. Its date matches the established
GovInfo annual-edition cutoff; the exception must remain explicit in comparison
results. The eCFR candidate is the official point-in-time API representation dated
2026-08-26. That date is a comparison target, not an asserted regulations cutoff.

The external bytes are intentionally not represented as staged: this registry does
not contain a checksum until a complete download succeeds. This avoids turning an
unverified URL, partial transfer, or moving `current` response into provenance.
