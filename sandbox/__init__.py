"""Sandbox integration clients for development and testing.

This package provides mock/simulated implementations of external service
clients (AA, GST, OCEN, Lender). It is config-driven: the main framework
loads these ONLY when INTEGRATION_MODE=sandbox.

This package is self-contained and excluded from production Docker images.
It MUST NOT be imported directly by any code in libs/ or services/ — all
access goes through libs.integrations.factory.
"""
