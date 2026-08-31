"""Adversarial runtime checks for every derived closed-vocabulary field."""

from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from open_us_law_coverage.derived import (
    ArtifactInput,
    ArtifactType,
    AssemblyStatus,
    AssemblyStrategy,
    AuthorityRole,
    DerivedArtifactProvenance,
    DocumentClass,
    DocumentClassificationAnnotation,
    IdentityMember,
    InputType,
    MemberRole,
    Operation,
    SourceDocumentAssembly,
    cfr_identity_group,
    compute_assembled_text_hash,
    detect_duplicate_rows,
    source_record_inputs,
)


def _hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def _artifacts():
    member = IdentityMember(
        source_record_id="r1",
        act_id="CFR_T17_S1",
        state="US",
        corpus="regulations",
        document_type="regulation",
        raw_text_hash=_hash("body"),
        physical_row_ordinal=0,
    )
    identity = cfr_identity_group([member])
    duplicate = detect_duplicate_rows(identity.group, [member])

    classification_provenance = DerivedArtifactProvenance.build(
        ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION,
        source_record_inputs(["r1"]),
        "classifier",
        "1",
    )
    classification = DocumentClassificationAnnotation(
        provenance=classification_provenance,
        document_class=DocumentClass.CODIFIED_CFR,
        authority_role=AuthorityRole.OPERATIVE_PRIMARY_LAW,
        confidence=1.0,
    )

    assembly_provenance = DerivedArtifactProvenance.build(
        ArtifactType.SOURCE_DOCUMENT_ASSEMBLY,
        source_record_inputs(["r1"]),
        "assembler",
        "1",
    )
    assembly = SourceDocumentAssembly(
        provenance=assembly_provenance,
        member_source_record_ids=("r1",),
        member_roles=(MemberRole.PRIMARY,),
        operations=(Operation.KEEP,),
        assembly_strategy=AssemblyStrategy.TRIVIAL_SINGLE_RECORD_V2,
        assembly_status=AssemblyStatus.COMPLETE,
        assembled_text="body",
        assembled_text_hash=compute_assembled_text_hash("body"),
    )
    return {
        "identity-group-scope": identity.group,
        "identity-group-status": identity.group,
        "identity-member-method": identity.members[0],
        "identity-member-confidence": identity.members[0],
        "classification-class": classification,
        "classification-role": classification,
        "quality-status": duplicate.annotations[0],
        "quality-flags": duplicate.annotations[0],
        "assembly-role": assembly,
        "assembly-operation": assembly,
        "assembly-strategy": assembly,
        "assembly-status": assembly,
    }


@pytest.mark.parametrize(
    "name, changes",
    [
        ("identity-group-scope", {"identity_scope": "made_up"}),
        ("identity-group-status", {"identity_status": "made_up"}),
        ("identity-member-method", {"segment_order_method": "made_up"}),
        ("identity-member-confidence", {"segment_order_confidence": "made_up"}),
        ("classification-class", {"document_class": "made_up"}),
        ("classification-role", {"authority_role": "made_up"}),
        ("quality-status", {"quality_status": "made_up"}),
        ("quality-flags", {"quality_flags": ("made_up",)}),
        ("assembly-role", {"member_roles": ("made_up",)}),
        ("assembly-operation", {"operations": ("made_up",)}),
        ("assembly-strategy", {"assembly_strategy": "made_up"}),
        ("assembly-status", {"assembly_status": "made_up"}),
    ],
)
def test_derived_artifacts_reject_values_outside_closed_vocabularies(name, changes):
    artifact = _artifacts()[name]
    with pytest.raises(ValueError, match="must be a"):
        replace(artifact, payload_hash="", **changes)


def test_provenance_edge_and_artifact_vocabularies_are_closed():
    with pytest.raises(ValueError, match="ArtifactInput.input_type"):
        ArtifactInput("made_up", "r1")

    provenance = DerivedArtifactProvenance.build(
        ArtifactType.QUALITY_ANNOTATION,
        source_record_inputs(["r1"]),
        "quality",
        "1",
    )
    with pytest.raises(ValueError, match="artifact_type"):
        replace(provenance, artifact_type="made_up")


def test_per_record_classification_rejects_extra_provenance_edges():
    provenance = DerivedArtifactProvenance.build(
        ArtifactType.DOCUMENT_CLASSIFICATION_ANNOTATION,
        (
            ArtifactInput(InputType.SOURCE_RECORD, "r1"),
            ArtifactInput(InputType.ANNOTATION, "unrelated"),
        ),
        "classifier",
        "1",
    )
    with pytest.raises(ValueError, match="exactly one"):
        DocumentClassificationAnnotation(
            provenance=provenance,
            document_class=DocumentClass.STATUTE,
            authority_role=AuthorityRole.OPERATIVE_PRIMARY_LAW,
            confidence=1.0,
        )
