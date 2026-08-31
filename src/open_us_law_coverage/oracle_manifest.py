"""Validated metadata for snapshot currency and edition-pinned human oracles."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .derived import ArtifactInput, InputType

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class CutoffStatus(StrEnum):
    ESTABLISHED = "established"
    UNRESOLVED = "unresolved"


class OracleKind(StrEnum):
    USLM = "uslm"
    ECFR = "ecfr"


def _parse_date(value: str, field_name: str) -> str:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an ISO date, got {value!r}") from exc
    return value


@dataclass(frozen=True, slots=True)
class OracleEdition:
    oracle_edition: str
    kind: OracleKind
    edition_date: str
    source_url: str
    local_path: str | None
    sha256: str | None

    def __post_init__(self) -> None:
        if not self.oracle_edition.startswith("oracle:"):
            raise ValueError("oracle_edition must be a stable 'oracle:' identifier")
        if not isinstance(self.kind, OracleKind):
            raise ValueError(f"kind must be an OracleKind, got {self.kind!r}")
        _parse_date(self.edition_date, "edition_date")
        if urlparse(self.source_url).scheme != "https":
            raise ValueError("source_url must use https")
        if (self.local_path is None) != (self.sha256 is None):
            raise ValueError("local_path and sha256 must either both be set or both be null")
        if self.sha256 is not None and not _SHA256_RE.fullmatch(self.sha256):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")

    @property
    def staged(self) -> bool:
        return self.local_path is not None

    def provenance_input(self) -> ArtifactInput:
        return ArtifactInput(InputType.ORACLE_EDITION, self.oracle_edition)


@dataclass(frozen=True, slots=True)
class CorpusCurrency:
    corpus: str
    snapshot_content_cutoff: str | None
    cutoff_status: CutoffStatus
    basis: str
    comparison_oracle_edition: str
    residual_skew_days: int | None

    def __post_init__(self) -> None:
        if not self.corpus or not self.basis:
            raise ValueError("corpus and basis must be non-empty")
        if not isinstance(self.cutoff_status, CutoffStatus):
            raise ValueError(
                f"cutoff_status must be a CutoffStatus, got {self.cutoff_status!r}"
            )
        if self.snapshot_content_cutoff is not None:
            _parse_date(self.snapshot_content_cutoff, "snapshot_content_cutoff")
        if (self.cutoff_status == CutoffStatus.ESTABLISHED) != (
            self.snapshot_content_cutoff is not None
        ):
            raise ValueError(
                "established cutoffs require a date; unresolved cutoffs require null"
            )
        if self.residual_skew_days is not None and self.cutoff_status != CutoffStatus.ESTABLISHED:
            raise ValueError("residual_skew_days requires an established cutoff")


@dataclass(frozen=True, slots=True)
class OracleManifest:
    snapshot: str
    dataset_revision: str
    repository_commit_date: str
    repository_commit_date_is_content_cutoff: bool
    editions: tuple[OracleEdition, ...]
    corpora: tuple[CorpusCurrency, ...]

    def __post_init__(self) -> None:
        _parse_date(self.repository_commit_date, "repository_commit_date")
        if self.repository_commit_date_is_content_cutoff:
            raise ValueError(
                "the dataset repository commit date is publication metadata, not a "
                "legal-content cutoff"
            )
        edition_ids = [edition.oracle_edition for edition in self.editions]
        if len(set(edition_ids)) != len(edition_ids):
            raise ValueError("oracle_edition identifiers must be unique")
        known = set(edition_ids)
        for corpus in self.corpora:
            if corpus.comparison_oracle_edition not in known:
                raise ValueError(
                    f"{corpus.corpus} references unknown oracle edition "
                    f"{corpus.comparison_oracle_edition!r}"
                )


def load_oracle_manifest(path: str | Path) -> OracleManifest:
    raw: dict[str, Any] = json.loads(Path(path).read_text())
    editions = tuple(
        OracleEdition(
            oracle_edition=item["oracle_edition"],
            kind=OracleKind(item["kind"]),
            edition_date=item["edition_date"],
            source_url=item["source_url"],
            local_path=item["local_path"],
            sha256=item["sha256"],
        )
        for item in raw["oracle_editions"]
    )
    corpora = tuple(
        CorpusCurrency(
            corpus=item["corpus"],
            snapshot_content_cutoff=item["snapshot_content_cutoff"],
            cutoff_status=CutoffStatus(item["cutoff_status"]),
            basis=item["basis"],
            comparison_oracle_edition=item["comparison_oracle_edition"],
            residual_skew_days=item["residual_skew_days"],
        )
        for item in raw["corpora"]
    )
    return OracleManifest(
        snapshot=raw["snapshot"],
        dataset_revision=raw["dataset_revision"],
        repository_commit_date=raw["repository_commit_date"],
        repository_commit_date_is_content_cutoff=raw[
            "repository_commit_date_is_content_cutoff"
        ],
        editions=editions,
        corpora=corpora,
    )
