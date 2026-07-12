"""Trust Graph domain models — graph nodes and edges for the proprietary moat."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from decimal import Decimal
from uuid import UUID  # noqa: TC003

from pydantic import BaseModel, Field


class GraphNode(BaseModel):
    """A node in the Trust Graph."""

    node_id: UUID
    node_type: str = Field(..., description="anchor|vendor|invoice|loan|lender")
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    created_at: datetime | None = None


class GraphEdge(BaseModel):
    """An edge in the Trust Graph."""

    source_id: UUID
    target_id: UUID
    edge_type: str = Field(..., description="supplies_to|attested_for|originated_from|repaid_to")
    weight: Decimal = Field(default=Decimal("1.0"))
    properties: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    created_at: datetime | None = None


class TrustScore(BaseModel):
    """Computed trust score for a vendor-anchor pair."""

    vendor_id: UUID
    anchor_id: UUID
    score: Decimal = Field(..., ge=0, le=100)
    components: TrustScoreComponents
    computed_at: datetime


class TrustScoreComponents(BaseModel):
    """Breakdown of trust score components."""

    attestation_score: Decimal = Field(
        default=Decimal("0"), description="Kind 1 attestation history"
    )
    repayment_score: Decimal = Field(default=Decimal("0"), description="On-time repayment rate")
    relationship_score: Decimal = Field(default=Decimal("0"), description="Longevity and volume")
    concentration_penalty: Decimal = Field(default=Decimal("0"), description="Single-anchor risk")
