"""Tests for structured logging and correlation ID."""

from __future__ import annotations

from libs.common.logging import (
    configure_logging,
    correlation_id_var,
    get_correlation_id,
    new_correlation_id,
)


def test_new_correlation_id_is_uuid4():
    cid = new_correlation_id()
    assert len(cid) == 36
    assert cid.count("-") == 4


def test_get_correlation_id_creates_if_empty():
    correlation_id_var.set("")
    cid = get_correlation_id()
    assert len(cid) == 36
    assert correlation_id_var.get() == cid


def test_get_correlation_id_reuses_existing():
    new_correlation_id()
    cid1 = get_correlation_id()
    cid2 = get_correlation_id()
    assert cid1 == cid2


def test_configure_logging_does_not_raise():
    configure_logging(json_output=True, log_level="DEBUG")
    configure_logging(json_output=False, log_level="INFO")
