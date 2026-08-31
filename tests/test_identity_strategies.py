"""M1A.5 closure Phase B — the concrete identity-strategy producers.

B.1 (1:1 strategies) runs ``CanonicalSourceRecord -> identity -> trivial assembly``
end-to-end over the hermetic fixture and asserts the chain composes a real record
with ``assembled_text == raw_text`` byte-for-byte. B.2 (regulations collision
strategies) exercises the multi-member group over synthetic members, preserving the
frozen M0.5A.1 semantics: physical-row-order ``segment_ordinal`` only, FR marked
ambiguous (never composed), occurrence-index disambiguation of byte-identical rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from open_us_law_coverage.derived import (
    IdentityMember,
    IdentityScope,
    IdentityStatus,
    SegmentOrderConfidence,
    SegmentOrderMethod,
    cfr_identity_group,
    check_payload_collisions,
    federal_register_document_group,
    identity_member,
    regulations_identity_group,
    resolve_single_record_identity,
)
from open_us_law_coverage.derived.assembly import (
    AssemblyStatus,
    assemble_trivial_single_record,
)
from open_us_law_coverage.derived.identity_strategies import (
    CFR_IDENTITY_V1,
    CONSTITUTION_ACT_ID_V1,
    FEDERAL_REGISTER_DOCUMENT_V1,
    STATE_REGULATION_V1,
    STATE_STATUTE_ACT_ID_V1,
    USC_ACT_ID_V1,
    state_regulation_identity_group,
)
from open_us_law_coverage.source_record import read_source_records
from tests.conftest import SNAPSHOT


# ---------------------------------------------------------------------------
# B.1 — the 1:1 strategies, over the real fixture.
# ---------------------------------------------------------------------------

def test_dispatch_picks_the_right_11_strategy(fixture_parquet: Path):
    records = read_source_records(fixture_parquet, SNAPSHOT)
    by_strategy = {}
    for rec in records:
        result = resolve_single_record_identity(rec)
        assert result is not None  # the fixture is all statutes/constitutions
        by_strategy.setdefault(result.group.strategy_name, []).append(rec)

    strategies = set(by_strategy)
    assert USC_ACT_ID_V1 in strategies          # USC_T42...
    assert STATE_STATUTE_ACT_ID_V1 in strategies  # STATE_AK... statute
    assert CONSTITUTION_ACT_ID_V1 in strategies   # SCONST_AK... constitution


def test_11_strategy_emits_a_resolved_single_member_group(fixture_parquet: Path):
    rec = read_source_records(fixture_parquet, SNAPSHOT)[0]  # USC statute
    result = resolve_single_record_identity(rec)
    assert result is not None
    group = result.group
    assert group.member_source_record_ids == (rec.source_record_id,)
    assert group.identity_status == IdentityStatus.RESOLVED
    assert group.identity_scope == IdentityScope.DOCUMENT
    assert len(result.members) == 1
    m = result.members[0]
    assert m.target_source_record_id == rec.source_record_id
    assert m.segment_order_method == SegmentOrderMethod.SINGLE_RECORD
    assert m.segment_order_confidence == SegmentOrderConfidence.NOT_APPLICABLE
    # provenance anchors to the physical row, never to the identity key.
    assert group.provenance.source_record_ids() == (rec.source_record_id,)
    assert group.source_identity_key not in {
        e.input_id for e in group.provenance.inputs
    }


def test_full_chain_identity_then_assembly_is_byte_for_byte(fixture_parquet: Path):
    """B.1 headline: the first end-to-end run of the interpretation stack over real
    records — identity groups a single record, assembly returns its text verbatim."""
    records = read_source_records(fixture_parquet, SNAPSHOT)
    produced = []
    for rec in records:
        result = resolve_single_record_identity(rec)
        assert result is not None
        asm = assemble_trivial_single_record(rec)
        # identity and assembly agree on the single physical member.
        assert result.group.member_source_record_ids == asm.member_source_record_ids
        produced.extend([result.group, *result.members, asm])
        if rec.raw_text is None:
            assert asm.assembly_status == AssemblyStatus.NONCOMPOSABLE
        else:
            assert asm.assembly_status == AssemblyStatus.COMPLETE
            assert asm.assembled_text == rec.raw_text  # not one byte changed
    # every artifact from the run coexists without an id/payload collision.
    check_payload_collisions(produced)


# ---------------------------------------------------------------------------
# B.2 — the regulations collision strategies, over synthetic members.
# ---------------------------------------------------------------------------

def _cfr_member(rid: str, ordinal: int, text_hash: str | None) -> IdentityMember:
    return IdentityMember(
        source_record_id=rid,
        act_id="CFR_T17_P240_S240.10b-5",
        state="US",
        corpus="regulations",
        document_type="regulation",
        raw_text_hash=text_hash,
        physical_row_ordinal=ordinal,
    )


def _fr_member(rid: str, ordinal: int, text_hash: str | None) -> IdentityMember:
    return IdentityMember(
        source_record_id=rid,
        act_id="FR_2026_12345",
        state="US",
        corpus="regulations",
        document_type="regulation",
        raw_text_hash=text_hash,
        physical_row_ordinal=ordinal,
    )


def test_cfr_multi_row_is_provisional_multisegment():
    # deliberately out of physical order to prove the strategy re-orders.
    members = [
        _cfr_member("r_c", 20, "hc"),
        _cfr_member("r_a", 5, "ha"),
        _cfr_member("r_b", 12, "hb"),
    ]
    result = cfr_identity_group(members)
    assert result.group.strategy_name == CFR_IDENTITY_V1
    assert result.group.identity_status == IdentityStatus.PROVISIONAL
    assert result.group.identity_scope == IdentityScope.SEGMENT
    # members are stored canonically (sorted) on the group; the annotations carry the
    # physical-row-order segment_ordinal.
    ordinals = {
        m.target_source_record_id: m.segment_ordinal for m in result.members
    }
    assert ordinals == {"r_a": 0, "r_b": 1, "r_c": 2}
    for m in result.members:
        assert m.segment_order_method == SegmentOrderMethod.PHYSICAL_ROW_ORDER
        assert m.segment_order_confidence == SegmentOrderConfidence.SNAPSHOT_OBSERVED
    check_payload_collisions([result.group, *result.members])


def test_fr_multi_row_is_ambiguous_numbering_bucket():
    members = [_fr_member("r1", 1, "h1"), _fr_member("r2", 99, "h2")]
    result = federal_register_document_group(members)
    assert result.group.strategy_name == FEDERAL_REGISTER_DOCUMENT_V1
    # co-numbered distinct captures: ambiguous, a numbering bucket, never composed.
    assert result.group.identity_status == IdentityStatus.AMBIGUOUS
    assert result.group.identity_scope == IdentityScope.NUMBERING_BUCKET


def test_byte_identical_rows_get_distinct_occurrence_indices():
    """M0.5A.1: occurrence_index disambiguates byte-identical duplicate rows within a
    group; the fingerprints differ only by that index."""
    members = [
        _cfr_member("r1", 1, "same"),
        _cfr_member("r2", 2, "same"),
    ]
    result = cfr_identity_group(members)
    fps = sorted(m.segment_fingerprint for m in result.members)
    assert fps == [
        "CFR_T17_P240_S240.10b-5|same|0",
        "CFR_T17_P240_S240.10b-5|same|1",
    ]


def test_single_row_regulation_act_id_is_degenerate_11():
    result = cfr_identity_group([_cfr_member("only", 3, "h")])
    assert result.group.member_source_record_ids == ("only",)
    assert result.group.identity_status == IdentityStatus.RESOLVED
    assert result.members[0].segment_order_method == SegmentOrderMethod.SINGLE_RECORD


def _state_reg_member(rid: str, ordinal: int) -> IdentityMember:
    return IdentityMember(
        source_record_id=rid,
        act_id="STATE_OH_ADC_117_3_11",
        state="OH",
        corpus="regulations",
        document_type="regulation",
        raw_text_hash=f"h{ordinal}",
        physical_row_ordinal=ordinal,
    )


def test_router_dispatches_by_namespace():
    """C.3 finding: collisions are not federal-only. The router sends CFR_/FR_/STATE_
    regulation groups to the right strategy."""
    cfr = regulations_identity_group([_cfr_member("a", 1, "h"), _cfr_member("b", 2, "g")])
    fr = regulations_identity_group([_fr_member("a", 1, "h"), _fr_member("b", 2, "g")])
    state = regulations_identity_group(
        [_state_reg_member("a", 1), _state_reg_member("b", 2)]
    )
    assert cfr.group.strategy_name == "cfr_identity_v1"
    assert cfr.group.identity_status == IdentityStatus.PROVISIONAL
    assert fr.group.strategy_name == "federal_register_document_v1"
    assert fr.group.identity_status == IdentityStatus.AMBIGUOUS
    assert state.group.strategy_name == "state_regulation_v1"
    assert state.group.identity_status == IdentityStatus.PROVISIONAL
    assert state.group.identity_scope == IdentityScope.SEGMENT


# ---------------------------------------------------------------------------
# Finding P1-2 — dispatch is by authoritative document_type, never the ambiguous
# STATE_* prefix.
# ---------------------------------------------------------------------------

@dataclass
class _FakeRecord:
    """A duck-typed stand-in for a CanonicalSourceRecord — the strategies read only
    ``.source_record_id`` / ``.column(name)`` / ``.source_file`` / ``.raw_text_hash`` /
    ``.physical_row_ordinal`` (via ``identity_member``)."""

    source_file: str
    _cols: dict
    source_record_id: str = "srr:sha256:x"
    raw_text_hash: str | None = "sha256:deadbeef"
    physical_row_ordinal: int = 0

    def column(self, name: str):
        return self._cols.get(name)


def _rec(act_id: str, document_type: str, *, state: str, source_file: str) -> _FakeRecord:
    return _FakeRecord(
        source_file=source_file,
        _cols={"act_id": act_id, "state": state, "document_type": document_type},
    )


def test_state_regulation_is_not_dispatched_as_a_statute():
    """A ``STATE_*`` *regulation* must return ``None`` from the 1:1 dispatcher — it is
    grouped by the collision strategies, never falsely resolved as a state statute."""
    reg = _rec(
        "STATE_OH_ADC_117_3_11", "regulation", state="OH",
        source_file="us_oh_regulations.parquet",
    )
    assert resolve_single_record_identity(reg) is None


def test_state_statute_with_same_prefix_still_dispatches_to_statute():
    """The same ``STATE_*`` prefix on a *statute* dispatches to the state-statute 1:1
    strategy — the prefix is shared, the authoritative ``document_type`` is not."""
    stat = _rec(
        "STATE_OH_RC_1_01", "statute", state="OH",
        source_file="us_oh_statutes.parquet",
    )
    result = resolve_single_record_identity(stat)
    assert result is not None
    assert result.group.strategy_name == STATE_STATUTE_ACT_ID_V1


def test_dispatch_uses_document_type_not_prefix():
    """Court-rules / guidance (no concrete 1:1 strategy, non-statute document_type)
    abstain to ``None`` rather than being force-fit by a prefix."""
    guidance = _rec(
        "STATE_OH_GUIDE_1", "guidance", state="OH",
        source_file="us_oh_guidance.parquet",
    )
    assert resolve_single_record_identity(guidance) is None


# ---------------------------------------------------------------------------
# Finding P2-5 — collision producers reject malformed / heterogeneous groups.
# ---------------------------------------------------------------------------

def test_cfr_group_rejects_mixed_namespace_members():
    """The adversarial group the review built: a CFR row and an FR row together. They
    have distinct act_ids, so they cannot share one grouping key — rejected, never
    labeled with the first member's key."""
    with pytest.raises(ValueError):
        cfr_identity_group([_cfr_member("a", 1, "h"), _fr_member("b", 2, "g")])


def test_cfr_group_rejects_a_statute_member():
    """A state statute smuggled into a CFR group is rejected on corpus/type."""
    statute = IdentityMember(
        source_record_id="s",
        act_id="CFR_T17_P240_S240.10b-5",
        state="US",
        corpus="statutes",
        document_type="statute",
        raw_text_hash="h",
        physical_row_ordinal=9,
    )
    with pytest.raises(ValueError):
        cfr_identity_group([_cfr_member("a", 1, "h"), statute])


def test_cfr_producer_rejects_a_wrong_namespace_group():
    """A homogeneous FR group handed to the CFR producer is rejected — each concrete
    producer validates its own namespace."""
    with pytest.raises(ValueError):
        cfr_identity_group([_fr_member("a", 1, "h"), _fr_member("b", 2, "g")])


def test_fr_producer_rejects_a_cfr_group():
    with pytest.raises(ValueError):
        federal_register_document_group([_cfr_member("a", 1, "h"), _cfr_member("b", 2, "g")])


def test_state_producer_rejects_a_cfr_group():
    with pytest.raises(ValueError):
        state_regulation_identity_group([_cfr_member("a", 1, "h"), _cfr_member("b", 2, "g")])


def test_regulation_group_rejects_empty_act_id():
    bad = IdentityMember(
        source_record_id="b",
        act_id=None,
        state="US",
        corpus="regulations",
        document_type="regulation",
        raw_text_hash="h",
        physical_row_ordinal=2,
    )
    with pytest.raises(ValueError):
        cfr_identity_group([_cfr_member("a", 1, "h"), bad])


def test_state_regulation_group_rejects_mixed_state():
    """The grouping key is `(state, corpus, act_id)` — not act_id alone. Two rows that
    share an act_id but sit under *different* states are two groups, not one, so a
    producer must reject them rather than key the pair from the first member's state.
    (A shared administrative-code numbering across states is exactly how a silent
    cross-jurisdiction merge would be born.)"""
    def member(rid: str, state: str, ordinal: int) -> IdentityMember:
        return IdentityMember(
            source_record_id=rid,
            act_id="STATE_ADC_109_1_1_03",
            state=state,
            corpus="regulations",
            document_type="regulation",
            raw_text_hash="h",
            physical_row_ordinal=ordinal,
        )

    with pytest.raises(ValueError):
        state_regulation_identity_group([member("a", "OH", 1), member("b", "IN", 2)])
