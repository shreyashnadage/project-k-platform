"""Tests for Trust Graph service."""

from __future__ import annotations

import uuid
from decimal import Decimal

from services.trust_graph.service import TrustGraphService


def test_add_node():
    svc = TrustGraphService()
    node = svc.add_node("vendor", {"name": "Test Vendor"})
    assert node.node_type == "vendor"
    assert svc.get_node(node.node_id) == node


def test_add_edge():
    svc = TrustGraphService()
    n1 = svc.add_node("vendor")
    n2 = svc.add_node("anchor")
    edge = svc.add_edge(n1.node_id, n2.node_id, "supplies_to")
    assert edge.edge_type == "supplies_to"
    assert len(svc.get_vendor_edges(n1.node_id)) == 1


def test_trust_score_zero_with_no_history():
    svc = TrustGraphService()
    vendor_id = uuid.uuid4()
    anchor_id = uuid.uuid4()
    score = svc.compute_trust_score(vendor_id, anchor_id)
    assert score.score == Decimal("0")


def test_trust_score_increases_with_attestations():
    svc = TrustGraphService()
    vendor_id = uuid.uuid4()
    anchor_id = uuid.uuid4()

    for _ in range(3):
        svc.record_attestation(vendor_id, anchor_id)

    score = svc.compute_trust_score(vendor_id, anchor_id)
    assert score.score > Decimal("0")
    assert score.components.attestation_score == Decimal("30")


def test_trust_score_with_repayments():
    svc = TrustGraphService()
    vendor_id = uuid.uuid4()
    anchor_id = uuid.uuid4()

    svc.record_attestation(vendor_id, anchor_id)
    svc.record_repayment(vendor_id, anchor_id, Decimal("100000"), on_time=True)
    svc.record_repayment(vendor_id, anchor_id, Decimal("200000"), on_time=True)
    svc.record_repayment(vendor_id, anchor_id, Decimal("150000"), on_time=False)

    score = svc.compute_trust_score(vendor_id, anchor_id)
    assert score.score > Decimal("0")
    assert score.components.repayment_score > Decimal("0")


def test_concentration_penalty():
    svc = TrustGraphService()
    vendor_id = uuid.uuid4()
    anchor_id = uuid.uuid4()

    for _ in range(10):
        svc.record_attestation(vendor_id, anchor_id)

    score = svc.compute_trust_score(vendor_id, anchor_id)
    assert score.components.concentration_penalty > Decimal("0")
