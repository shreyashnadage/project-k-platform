"""Protocol-based identity and authorization layer.

Application code depends ONLY on the protocols defined here, never on
concrete identity providers (Keycloak, Kratos, Auth0, etc.) directly.
Provider selection is config-driven via identity.yaml + libs/auth/factory.py.
"""
