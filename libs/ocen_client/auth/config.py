"""OCEN configuration — loaded from environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class OcenConfig(BaseSettings):
    """OCEN network configuration."""

    client_id: str = ""
    client_secret: str = ""
    token_url: str = "https://auth.ocen.network/realms/dev/protocol/openid-connect/token"
    registry_base_url: str = "https://dev.ocen.network/service"
    heartbeat_url: str = "https://analytics-dev.ocen.network/ocen/v4/event"
    jwt_issuer: str = "https://auth.ocen.network/realms/dev"

    participant_id: str = ""
    org_id: str = ""
    product_id: str = ""
    product_network_id: str = ""

    keypair_path: str = "secrets/ocen_keypair.json"

    model_config = {"env_prefix": "OCEN_"}


def get_ocen_config() -> OcenConfig:
    return OcenConfig()
