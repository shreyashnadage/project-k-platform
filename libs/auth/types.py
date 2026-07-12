"""Provider-agnostic identity and token types.

All auth adapters return these types — application code never handles
provider-specific response shapes.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class OrgType(str, Enum):
    vendor = "vendor"
    anchor = "anchor"


class TokenClaims(BaseModel):
    """Decoded, validated JWT claims — provider-agnostic."""

    subject: str = Field(description="Unique identity ID (sub claim)")
    issuer: str = Field(default="", description="Token issuer (iss claim)")
    audience: str | list[str] = Field(default="", description="Intended audience")
    roles: set[str] = Field(default_factory=set, description="Resolved roles")
    org_id: str | None = Field(default=None, description="Tenant/org identifier")
    org_type: OrgType | None = Field(default=None, description="Organization type")
    email: str | None = Field(default=None)
    phone: str | None = Field(default=None)
    expires_at: datetime | None = Field(default=None)
    raw: dict = Field(default_factory=dict, description="Full decoded token for edge cases")


class IdentityRecord(BaseModel):
    """A resolved identity from the identity provider."""

    identity_id: str = Field(description="Provider-assigned identity ID")
    org_type: OrgType = Field(default=OrgType.vendor)
    traits: dict = Field(default_factory=dict, description="Identity traits (phone, gstin, etc.)")
    state: str = Field(default="active", description="active | inactive | suspended")
    created_at: datetime | None = Field(default=None)
    verified: bool = Field(default=False)


class AuthCredentials(BaseModel):
    """Credentials for authentication — OTP, password, etc."""

    identifier: str = Field(description="Phone number, email, or username")
    credential_type: str = Field(default="otp", description="otp | password | social")
    credential_value: str = Field(default="", description="OTP code, password, etc.")


class TokenPair(BaseModel):
    """Issued token pair after successful authentication."""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int = Field(description="Seconds until access_token expires")
    id_token: str | None = None
