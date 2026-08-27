"""M1A.5 acceptance — the multi-input provenance DAG.

Invariants (``PROPOSAL.md`` "Data contracts", DerivedArtifactProvenance):

* ``artifact_id`` is content-addressed and **order-independent** in ``inputs``.
* ``generated_at`` is **excluded** from ``artifact_id`` (a byte-identical
  recompute yields the same id).
* different member sets never collide; changing producer/version/config changes
  the id.
"""

from __future__ import annotations

import dataclasses

import pytest

from open_us_law_coverage.derived import (
    ArtifactInput,
    ArtifactType,
    DerivedArtifactProvenance,
    InputType,
    compute_artifact_id,
    source_record_inputs,
)


def _edges(*ids: str) -> tuple[ArtifactInput, ...]:
    return source_record_inputs(list(ids))


def test_artifact_id_is_order_independent():
    a = compute_artifact_id(ArtifactType.SOURCE_DOCUMENT_ASSEMBLY, _edges("r1", "r2", "r3"), "p", "1")
    b = compute_artifact_id(ArtifactType.SOURCE_DOCUMENT_ASSEMBLY, _edges("r3", "r1", "r2"), "p", "1")
    assert a == b


def test_equal_id_implies_equal_serialized_inputs():
    """Review P1: stored inputs are canonicalized, so equal ``artifact_id`` implies a
    byte-identical object — reversing the inputs yields the *same* serialized tuple,
    not just the same id."""
    fwd = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY, _edges("r1", "r2", "r3"), "p", "1"
    )
    rev = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY, _edges("r3", "r2", "r1"), "p", "1"
    )
    assert fwd.artifact_id == rev.artifact_id
    assert fwd.inputs == rev.inputs            # canonical stored order
    assert fwd == rev                          # fully equal serialized objects
    # and the canonical order is deterministic (sorted by the hashing key).
    assert list(fwd.inputs) == sorted(fwd.inputs, key=lambda e: (str(e.input_type), e.input_id))


def test_directly_constructed_provenance_is_canonicalized():
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY, _edges("z", "a", "m"), "p", "1"
    )
    assert [e.input_id for e in prov.inputs] == ["a", "m", "z"]


def test_generated_at_excluded_from_id():
    p1 = DerivedArtifactProvenance.build(
        ArtifactType.QUALITY_ANNOTATION, _edges("r1"), "p", "1", generated_at="2026-08-25T00:00:00Z"
    )
    p2 = DerivedArtifactProvenance.build(
        ArtifactType.QUALITY_ANNOTATION, _edges("r1"), "p", "1", generated_at="1999-01-01T00:00:00Z"
    )
    assert p1.artifact_id == p2.artifact_id
    assert p1.generated_at != p2.generated_at


def test_different_member_sets_do_not_collide():
    a = compute_artifact_id(ArtifactType.SOURCE_DOCUMENT_ASSEMBLY, _edges("r1", "r2"), "p", "1")
    b = compute_artifact_id(ArtifactType.SOURCE_DOCUMENT_ASSEMBLY, _edges("r1", "r2", "r3"), "p", "1")
    assert a != b


def test_producer_identity_changes_id():
    base = _edges("r1")
    ids = {
        compute_artifact_id(ArtifactType.QUALITY_ANNOTATION, base, "p", "1"),
        compute_artifact_id(ArtifactType.QUALITY_ANNOTATION, base, "p", "2"),
        compute_artifact_id(ArtifactType.QUALITY_ANNOTATION, base, "q", "1"),
        compute_artifact_id(ArtifactType.QUALITY_ANNOTATION, base, "p", "1", config_hash="cfg"),
        compute_artifact_id(ArtifactType.SOURCE_IDENTITY_ANNOTATION, base, "p", "1"),
    }
    assert len(ids) == 5  # every distinguishing field moves the id


def test_input_type_participates_in_id():
    same_id = "x"
    a = compute_artifact_id(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY,
        (ArtifactInput(InputType.SOURCE_RECORD, same_id),),
        "p",
        "1",
    )
    b = compute_artifact_id(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY,
        (ArtifactInput(InputType.ORACLE_EDITION, same_id),),
        "p",
        "1",
    )
    assert a != b


def test_source_record_ids_helper_filters_by_edge_type():
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY,
        (
            ArtifactInput(InputType.SOURCE_RECORD, "r1"),
            ArtifactInput(InputType.SOURCE_RECORD, "r2"),
            ArtifactInput(InputType.ORACLE_EDITION, "eCFR-2026-08"),
        ),
        "p",
        "1",
    )
    assert prov.source_record_ids() == ("r1", "r2")
    assert prov.input_ids_of(InputType.ORACLE_EDITION) == ("eCFR-2026-08",)


def test_provenance_is_frozen():
    prov = DerivedArtifactProvenance.build(ArtifactType.QUALITY_ANNOTATION, _edges("r1"), "p", "1")
    with pytest.raises(dataclasses.FrozenInstanceError):
        prov.producer_version = "2"  # type: ignore[misc]


# --- review P6: model invariants on directly-constructed provenance -------


def test_directly_constructed_inconsistent_id_is_rejected():
    """A directly-built provenance whose stored id does not content-address its
    inputs is a corrupt DAG node."""
    with pytest.raises(ValueError, match="inconsistent"):
        DerivedArtifactProvenance(
            artifact_id="art:sha256:deadbeef",  # not a real hash of the inputs
            artifact_type=ArtifactType.QUALITY_ANNOTATION,
            inputs=_edges("r1"),
            producer_name="p",
            producer_version="1",
        )


def test_duplicate_edges_are_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        DerivedArtifactProvenance.build(
            ArtifactType.QUALITY_ANNOTATION,
            (ArtifactInput(InputType.SOURCE_RECORD, "r1"),
             ArtifactInput(InputType.SOURCE_RECORD, "r1")),
            "p",
            "1",
        )


def test_empty_producer_identifiers_rejected():
    with pytest.raises(ValueError):
        DerivedArtifactProvenance.build(ArtifactType.QUALITY_ANNOTATION, _edges("r1"), "", "1")
    with pytest.raises(ValueError):
        DerivedArtifactProvenance.build(ArtifactType.QUALITY_ANNOTATION, _edges("r1"), "p", "")


def test_empty_input_id_rejected():
    with pytest.raises(ValueError):
        DerivedArtifactProvenance.build(
            ArtifactType.QUALITY_ANNOTATION, (ArtifactInput(InputType.SOURCE_RECORD, ""),), "p", "1"
        )


def test_evidence_confidence_range_enforced():
    from open_us_law_coverage.derived import Evidence

    Evidence("k", "d")  # None is fine
    Evidence("k", "d", confidence=0.0)
    Evidence("k", "d", confidence=1.0)
    with pytest.raises(ValueError):
        Evidence("k", "d", confidence=1.5)
    with pytest.raises(ValueError):
        Evidence("k", "d", confidence=-0.1)
