"""OCEN Registry data models — participant and product network discovery."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Participant(BaseModel):
    """Organization registered on the OCEN network."""

    id: str = ""
    name: str = ""
    status: str = "ACTIVE"


class ParticipantDetail(BaseModel):
    """Participant role details from the OCEN Registry."""

    id: str
    participant_role: str = Field(default="LOAN_AGENT", alias="participantRole")
    kc_client_id: str = Field(default="", alias="kcClientId")
    public_key: str = Field(default="", alias="publicKey")
    base_url: str = Field(default="", alias="baseUrl")
    is_approved: bool = Field(default=False, alias="isApproved")
    participant: Participant | None = None

    model_config = {"populate_by_name": True}


class ProductNetworkDetail(BaseModel):
    """Product network with participating loan agents and lenders."""

    loan_agents: list[ParticipantDetail] = Field(default_factory=list, alias="LOAN_AGENT")
    lenders: list[ParticipantDetail] = Field(default_factory=list, alias="LENDER")

    model_config = {"populate_by_name": True}
