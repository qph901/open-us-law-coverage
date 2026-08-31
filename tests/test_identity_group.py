"""M1A.5 A.1 acceptance — the identity group + per-member shape.

Identity is the ``DuplicateScope`` analogue (D1): a :class:`SourceIdentityGroup`
content-addressed by the complete member set, and one
:class:`SourceIdentityMemberAnnotation` per member naming ``[group, this record]``
as inputs. These are the adversarial contract tests for the shape — malformed
direct construction must be rejected, the 1:1 case is the degenerate single-member
group, and a membership change re-hashes the group and every member annotation.
"""

from __future__ import annotations

import pytest

from open_us_law_coverage.derived import (
    ArtifactInput,
    ArtifactType,
    DerivedArtifactProvenance,
    IdentityScope,
    IdentityStatus,
    InputType,
    SegmentOrderConfidence,
    SegmentOrderMethod,
    SourceIdentityGroup,
    SourceIdentityMemberAnnotation,
    check_payload_collisions,
    source_record_inputs,
)


def _group(members, *, strategy="cfr_identity_v1", key="K", status=IdentityStatus.RESOLVED):
    canonical = tuple(sorted(members))
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_GROUP,
        source_record_inputs(canonical),
        "identity_strategy",
        "1",
    )
    return SourceIdentityGroup(
        provenance=prov,
        strategy_name=strategy,
        source_identity_key=key,
        member_source_record_ids=canonical,
        identity_scope=IdentityScope.DOCUMENT,
        identity_status=status,
        confidence=1.0,
    )


def _member(group, target, **overrides):
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION,
        (
            ArtifactInput(InputType.ANNOTATION, group.provenance.artifact_id),
            ArtifactInput(InputType.SOURCE_RECORD, target),
        ),
        "identity_strategy",
        "1",
    )
    fields = dict(provenance=prov, target_source_record_id=target)
    fields.update(overrides)
    return SourceIdentityMemberAnnotation(**fields)


# --- happy path ---------------------------------------------------------------


def test_multi_member_group_and_annotations_construct():
    group = _group(["r3", "r1", "r2"])
    assert group.member_source_record_ids == ("r1", "r2", "r3")  # canonical
    assert group.payload_hash.startswith("pay:sha256:")
    members = [_member(group, m) for m in group.member_source_record_ids]
    check_payload_collisions([group, *members])
    for m in members:
        assert m.payload_hash.startswith("pay:sha256:")


def test_single_member_is_the_degenerate_11_case():
    """The 1:1 case: a single-member group with single_record / not_applicable."""
    group = _group(["r1"])
    ann = _member(
        group,
        "r1",
        segment_order_method=SegmentOrderMethod.SINGLE_RECORD,
        segment_order_confidence=SegmentOrderConfidence.NOT_APPLICABLE,
        segment_ordinal=0,
    )
    assert group.member_source_record_ids == ("r1",)
    assert ann.segment_order_method == SegmentOrderMethod.SINGLE_RECORD


def test_segment_fields_bind_to_the_member_not_the_group():
    """D1 rationale: the scalar segment fields live on the per-member annotation, so
    two members carry distinct fingerprints without an unbound scalar on the group."""
    group = _group(["r1", "r2"])
    a = _member(group, "r1", segment_fingerprint="fp-r1", segment_ordinal=0)
    b = _member(group, "r2", segment_fingerprint="fp-r2", segment_ordinal=1)
    assert a.segment_fingerprint != b.segment_fingerprint
    assert a.provenance.artifact_id != b.provenance.artifact_id


# --- group invariants ---------------------------------------------------------


def test_group_rejects_wrong_provenance_type():
    prov = DerivedArtifactProvenance.build(
        ArtifactType.QUALITY_ANNOTATION, source_record_inputs(["r1"]), "p", "1"
    )
    with pytest.raises(ValueError, match="artifact_type"):
        SourceIdentityGroup(
            provenance=prov,
            strategy_name="s",
            source_identity_key="K",
            member_source_record_ids=("r1",),
            identity_scope=IdentityScope.RECORD,
            identity_status=IdentityStatus.RESOLVED,
            confidence=1.0,
        )


def test_group_rejects_members_disagreeing_with_provenance():
    good = _group(["r1", "r2"])
    with pytest.raises(ValueError, match="must equal the provenance"):
        SourceIdentityGroup(
            provenance=good.provenance,
            strategy_name="s",
            source_identity_key="K",
            member_source_record_ids=("r1", "r2", "r3"),  # r3 not in provenance
            identity_scope=IdentityScope.DOCUMENT,
            identity_status=IdentityStatus.RESOLVED,
            confidence=1.0,
        )


def test_group_rejects_unsorted_and_duplicate_members():
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_GROUP, source_record_inputs(["r1", "r2"]), "p", "1"
    )
    with pytest.raises(ValueError, match="sorted"):
        SourceIdentityGroup(
            provenance=prov,
            strategy_name="s",
            source_identity_key="K",
            member_source_record_ids=("r2", "r1"),  # unsorted
            identity_scope=IdentityScope.DOCUMENT,
            identity_status=IdentityStatus.RESOLVED,
            confidence=1.0,
        )
    dup_prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_GROUP, source_record_inputs(["r1"]), "p", "1"
    )
    with pytest.raises(ValueError, match="duplicate"):
        SourceIdentityGroup(
            provenance=dup_prov,
            strategy_name="s",
            source_identity_key="K",
            member_source_record_ids=("r1", "r1"),
            identity_scope=IdentityScope.DOCUMENT,
            identity_status=IdentityStatus.RESOLVED,
            confidence=1.0,
        )


def test_group_rejects_empty_key_and_out_of_range_confidence():
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_GROUP, source_record_inputs(["r1"]), "p", "1"
    )
    with pytest.raises(ValueError, match="source_identity_key"):
        SourceIdentityGroup(
            provenance=prov, strategy_name="s", source_identity_key="",
            member_source_record_ids=("r1",), identity_scope=IdentityScope.RECORD,
            identity_status=IdentityStatus.RESOLVED, confidence=1.0,
        )
    with pytest.raises(ValueError, match="confidence"):
        SourceIdentityGroup(
            provenance=prov, strategy_name="s", source_identity_key="K",
            member_source_record_ids=("r1",), identity_scope=IdentityScope.RECORD,
            identity_status=IdentityStatus.RESOLVED, confidence=1.5,
        )


# --- member-annotation invariants --------------------------------------------


def test_member_rejects_target_not_matching_source_edge():
    group = _group(["r1", "r2"])
    # provenance names r1 as the source edge, but the object claims target r2.
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION,
        (
            ArtifactInput(InputType.ANNOTATION, group.provenance.artifact_id),
            ArtifactInput(InputType.SOURCE_RECORD, "r1"),
        ),
        "identity_strategy",
        "1",
    )
    with pytest.raises(ValueError, match="exactly its target"):
        SourceIdentityMemberAnnotation(provenance=prov, target_source_record_id="r2")


def test_member_requires_group_annotation_edge():
    """A member annotation with no annotation edge is not anchored to any group."""
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION,
        source_record_inputs(["r1"]),  # only the source_record edge, no group
        "identity_strategy",
        "1",
    )
    with pytest.raises(ValueError, match="annotation input"):
        SourceIdentityMemberAnnotation(provenance=prov, target_source_record_id="r1")


def test_member_rejects_wrong_provenance_type():
    group = _group(["r1"])
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_GROUP,
        (
            ArtifactInput(InputType.ANNOTATION, group.provenance.artifact_id),
            ArtifactInput(InputType.SOURCE_RECORD, "r1"),
        ),
        "identity_strategy",
        "1",
    )
    with pytest.raises(ValueError, match="artifact_type"):
        SourceIdentityMemberAnnotation(provenance=prov, target_source_record_id="r1")


def test_member_payload_hash_validated():
    group = _group(["r1"])
    prov = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_IDENTITY_MEMBER_ANNOTATION,
        (
            ArtifactInput(InputType.ANNOTATION, group.provenance.artifact_id),
            ArtifactInput(InputType.SOURCE_RECORD, "r1"),
        ),
        "identity_strategy",
        "1",
    )
    with pytest.raises(ValueError, match="payload_hash"):
        SourceIdentityMemberAnnotation(
            provenance=prov,
            target_source_record_id="r1",
            payload_hash="pay:sha256:wrong",
        )
