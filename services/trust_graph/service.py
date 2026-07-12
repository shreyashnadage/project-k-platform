"""Trust Graph service — builds and queries the proprietary data moat.

The Trust Graph is the ONLY system that sees:
1. Anchor attestation (Kind 1 events)
2. Loan origination events
3. Repayment outcome events

This combination IS the moat — no single lender or anchor sees all three.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from .models import GraphEdge, GraphNode, TrustScore, TrustScoreComponents

logger = structlog.get_logger()


class TrustGraphService:
    """In-memory Trust Graph for Phase 2. Production uses PostgreSQL + Apache AGE."""

    def __init__(self) -> None:
        self._nodes: dict[uuid.UUID, GraphNode] = {}
        self._edges: list[GraphEdge] = []
        self._attestations: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
        self._repayments: dict[tuple[uuid.UUID, uuid.UUID], list[dict[str, Any]]] = {}

    def add_node(self, node_type: str, properties: dict[str, Any] | None = None) -> GraphNode:
        node = GraphNode(
            node_id=uuid.uuid4(),
            node_type=node_type,
            properties=properties or {},
            created_at=datetime.now(UTC),
        )
        self._nodes[node.node_id] = node
        return node

    def add_edge(
        self,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        edge_type: str,
        weight: Decimal = Decimal("1.0"),
        properties: dict[str, Any] | None = None,
    ) -> GraphEdge:
        edge = GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            properties=properties or {},
            created_at=datetime.now(UTC),
        )
        self._edges.append(edge)
        return edge

    def record_attestation(self, vendor_id: uuid.UUID, anchor_id: uuid.UUID) -> None:
        key = (vendor_id, anchor_id)
        self._attestations[key] = self._attestations.get(key, 0) + 1
        logger.info("attestation_recorded", vendor_id=str(vendor_id), anchor_id=str(anchor_id))

    def record_repayment(
        self,
        vendor_id: uuid.UUID,
        anchor_id: uuid.UUID,
        amount: Decimal,
        on_time: bool,
    ) -> None:
        key = (vendor_id, anchor_id)
        if key not in self._repayments:
            self._repayments[key] = []
        self._repayments[key].append({"amount": amount, "on_time": on_time})
        logger.info("repayment_recorded", vendor_id=str(vendor_id), on_time=on_time)

    def compute_trust_score(self, vendor_id: uuid.UUID, anchor_id: uuid.UUID) -> TrustScore:
        key = (vendor_id, anchor_id)

        attestation_count = self._attestations.get(key, 0)
        attestation_score = min(Decimal(attestation_count) * Decimal("10"), Decimal("30"))

        repayments = self._repayments.get(key, [])
        if repayments:
            on_time_count = sum(1 for r in repayments if r["on_time"])
            repayment_score = Decimal(on_time_count) / Decimal(len(repayments)) * Decimal("40")
        else:
            repayment_score = Decimal("0")

        relationship_score = min(
            Decimal(attestation_count + len(repayments)) * Decimal("2"), Decimal("20")
        )

        total_attestations = sum(self._attestations.values())
        if total_attestations > 0:
            concentration = Decimal(attestation_count) / Decimal(total_attestations)
            concentration_penalty = max(
                Decimal("0"), (concentration - Decimal("0.5")) * Decimal("20")
            )
        else:
            concentration_penalty = Decimal("0")

        components = TrustScoreComponents(
            attestation_score=attestation_score,
            repayment_score=repayment_score,
            relationship_score=relationship_score,
            concentration_penalty=concentration_penalty,
        )

        total = attestation_score + repayment_score + relationship_score - concentration_penalty
        score = max(Decimal("0"), min(total, Decimal("100")))

        return TrustScore(
            vendor_id=vendor_id,
            anchor_id=anchor_id,
            score=score,
            components=components,
            computed_at=datetime.now(UTC),
        )

    def get_vendor_edges(self, vendor_id: uuid.UUID) -> list[GraphEdge]:
        return [e for e in self._edges if e.source_id == vendor_id or e.target_id == vendor_id]

    def get_node(self, node_id: uuid.UUID) -> GraphNode | None:
        return self._nodes.get(node_id)
