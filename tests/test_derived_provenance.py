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
        compute_artifact_id(ArtifactType.SOURCE_IDENTITY_GROUP, base, "p", "1"),
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


# --- NEXT.md D2: payload_hash (semantic content address) + the tripwire --------


def test_payload_hash_is_order_and_type_stable():
    """Equal semantic bodies hash equally; tuples/lists and enum members serialize
    to the same canonical bytes."""
    from open_us_law_coverage.derived import Evidence, compute_payload_hash

    a = compute_payload_hash(
        ArtifactType.QUALITY_ANNOTATION,
        {"flags": ["duplicate_row"], "evidence": [Evidence("k", "d", confidence=1.0)]},
    )
    b = compute_payload_hash(
        ArtifactType.QUALITY_ANNOTATION,
        {"evidence": [Evidence("k", "d", confidence=1.0)], "flags": ("duplicate_row",)},
    )
    assert a == b


def test_payload_hash_distinguishes_body_and_type():
    from open_us_law_coverage.derived import compute_payload_hash

    base = {"document_class": "statute", "confidence": 1.0}
    changed = {"document_class": "regulation", "confidence": 1.0}
    assert compute_payload_hash(ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION, base) != (
        compute_payload_hash(ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION, changed)
    )
    # same body, different artifact_type -> different hash (no cross-type collision).
    assert compute_payload_hash(ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION, base) != (
        compute_payload_hash(ArtifactType.QUALITY_ANNOTATION, base)
    )


def test_non_serializable_payload_field_raises():
    from open_us_law_coverage.derived import compute_payload_hash

    with pytest.raises(TypeError):
        compute_payload_hash(ArtifactType.QUALITY_ANNOTATION, {"x": object()})


def _classification(document_class, *, rid="r1"):
    """A minimal directly-constructed classification annotation for tripwire tests."""
    from open_us_law_coverage.derived import (
        AuthorityRole,
        DocumentClassificationAnnotation,
    )

    prov = DerivedArtifactProvenance.build(
        ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION,
        _edges(rid),
        "classifier",
        "1",
    )
    return DocumentClassificationAnnotation(
        provenance=prov,
        document_class=document_class,
        authority_role=AuthorityRole.OPERATIVE_PRIMARY_LAW,
        confidence=1.0,
    )


def test_payload_hash_assigned_and_validated_on_construction():
    """A directly-built artifact fills its payload_hash; a hand-set wrong one raises."""
    from open_us_law_coverage.derived import (
        AuthorityRole,
        DocumentClass,
        DocumentClassificationAnnotation,
    )

    ann = _classification(DocumentClass.STATUTE)
    assert ann.payload_hash.startswith("pay:sha256:")
    prov = ann.provenance
    with pytest.raises(ValueError, match="payload_hash"):
        DocumentClassificationAnnotation(
            provenance=prov,
            document_class=DocumentClass.STATUTE,
            authority_role=AuthorityRole.OPERATIVE_PRIMARY_LAW,
            confidence=1.0,
            payload_hash="pay:sha256:not-the-real-body-hash",
        )


def test_equal_id_unequal_payload_tripwire_fires():
    """NEXT.md D2: two artifacts with the same artifact_id but different bodies — the
    unbumped-producer-change signature — must raise, not silently overwrite."""
    from open_us_law_coverage.derived import (
        DocumentClass,
        PayloadCollisionError,
        check_payload_collisions,
    )

    good = _classification(DocumentClass.STATUTE)
    # Same provenance (=> same artifact_id) but a different conclusion body: exactly
    # what a deterministic producer emits if its logic changes without a version bump.
    drifted = dataclasses.replace(good, document_class=DocumentClass.REGULATION, payload_hash="")
    assert good.provenance.artifact_id == drifted.provenance.artifact_id
    assert good.payload_hash != drifted.payload_hash

    check_payload_collisions([good, good])  # same body twice is fine
    with pytest.raises(PayloadCollisionError):
        check_payload_collisions([good, drifted])
