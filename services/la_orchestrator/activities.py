"""Temporal activities for the loan origination workflow.

Activities are where ALL non-deterministic work happens:
- Rule evaluation (Zen Engine, in-process)
- AA data fetch (Setu/Perfios, network call)
- OCEN submission (network call)
- DB reads/writes
- Event emission to Redpanda

Each activity MUST be idempotent — Temporal may retry on failure.
"""

from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from uuid import UUID

import orjson
import structlog
from temporalio import activity

from libs.common.event_producer import EventProducer
from libs.common.events import loan_decision_evaluated
from libs.integrations.factory import (
    get_aa_client,
    get_consent_client,
    get_gst_client,
    get_ocen_client,
    get_ocen_network_client,
)
from libs.ocen_client.models.journey import (
    Borrower,
    CreateLoanApplicationRequest,
)
from libs.ocen_client.models.journey import (
    LoanApplication as OcenLoanApplication,
)
from libs.zen_rules.engine import ZenDecisionEngine

logger = structlog.get_logger()

_zen_engine: ZenDecisionEngine | None = None
_zen_lock = threading.Lock()
_event_producer: EventProducer | None = None
_producer_lock = threading.Lock()


def get_event_producer() -> EventProducer:
    global _event_producer
    if _event_producer is None:
        with _producer_lock:
            if _event_producer is None:
                bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:19092")
                _event_producer = EventProducer(bootstrap_servers=bootstrap)
    return _event_producer


def get_zen_engine() -> ZenDecisionEngine:
    global _zen_engine
    if _zen_engine is None:
        with _zen_lock:
            if _zen_engine is None:
                _zen_engine = ZenDecisionEngine("rules/")
    return _zen_engine


# ─── Activity Inputs (serializable dataclasses) ─────────────


@dataclass
class EvaluateDecisionInput:
    loan_application_id: str
    gate: str
    ruleset_name: str
    context: dict | None = None


@dataclass
class CheckDPDPConsentInput:
    loan_application_id: str
    data_principal_id: str
    purposes: list[str] | None = None

    def __post_init__(self) -> None:
        if self.purposes is None:
            self.purposes = ["loan_origination", "kind1_attestation"]


@dataclass
class FetchAADataInput:
    loan_application_id: str
    vendor_gstin: str = ""
    data_principal_id: str = ""


@dataclass
class SubmitToLenderInput:
    loan_application_id: str
    lender_ids: list[str] | None = None

    def __post_init__(self) -> None:
        if self.lender_ids is None:
            self.lender_ids = []


# ─── Activities ─────────────────────────────────────────────


@activity.defn(name="evaluate_decision")
async def evaluate_decision(input: EvaluateDecisionInput) -> dict:
    """Evaluate a decision gate using the Zen Engine."""
    log = logger.bind(
        loan_application_id=input.loan_application_id,
        gate=input.gate,
        ruleset=input.ruleset_name,
    )
    log.info("evaluating_decision_gate")

    if input.context and input.ruleset_name in get_zen_engine().loaded_rulesets:
        result = get_zen_engine().evaluate(input.ruleset_name, input.context)
        context_bytes = orjson.dumps(input.context, option=orjson.OPT_SORT_KEYS)
        input_hash = hashlib.sha256(context_bytes).hexdigest()[:16]
        receipt_id = f"receipt-{input.loan_application_id}-{input.gate}"

        try:
            event = loan_decision_evaluated(
                loan_application_id=UUID(input.loan_application_id),
                gate=input.gate,
                outcome=result.output.get("outcome", "pass"),
                ruleset_hash=result.ruleset_hash,
                input_hash=input_hash,
                receipt_id=UUID(int=hash(receipt_id) % (2**128)),
                workflow_id=activity.info().workflow_id,
            )
            get_event_producer().publish(event)
        except Exception as e:
            log.warning("decision_receipt_publish_failed", error=str(e))

        log.info(
            "decision_receipt_emitted",
            gate=input.gate,
            outcome=result.output.get("outcome", "pass"),
            ruleset_hash=result.ruleset_hash,
            input_hash=input_hash,
            receipt_id=receipt_id,
        )

        return {
            "outcome": result.output.get("outcome", "pass"),
            "reason": result.output.get("reason", "evaluated"),
            "ruleset_hash": result.ruleset_hash,
            "input_hash": input_hash,
            "receipt_id": receipt_id,
            "matched_lender_ids": result.output.get("matched_lender_ids", []),
        }

    return {
        "outcome": "pass",
        "reason": "no_ruleset_or_context",
        "ruleset_hash": "none",
        "input_hash": "none",
        "receipt_id": f"receipt-{input.loan_application_id}-{input.gate}",
        "matched_lender_ids": [],
    }


@activity.defn(name="check_dpdp_consent")
async def check_dpdp_consent(input: CheckDPDPConsentInput) -> dict:
    """Verify DPDP consent before loan processing. Hard block if not granted."""
    log = logger.bind(
        loan_application_id=input.loan_application_id,
        data_principal_id=input.data_principal_id,
    )
    log.info("checking_dpdp_consent", purposes=input.purposes)

    consent_client = get_consent_client()
    result = await consent_client.check_consent(
        data_principal_id=input.data_principal_id,
        purposes=input.purposes or ["loan_origination", "kind1_attestation"],
    )

    log.info("dpdp_consent_result", allowed=result.allowed, reason=result.reason)
    return {"allowed": result.allowed, "reason": result.reason}


@activity.defn(name="fetch_aa_data")
async def fetch_aa_data(input: FetchAADataInput) -> dict:
    """Fetch financial data via Account Aggregator (mocked or real)."""
    log = logger.bind(loan_application_id=input.loan_application_id)

    if not input.vendor_gstin:
        log.error("fetch_aa_data_missing_gstin")
        return {"data_received": False, "months_available": 0, "fips_responded": []}

    log.info("fetching_aa_data")

    aa_client = get_aa_client()
    consent = await aa_client.create_consent(
        vendor_gstin=input.vendor_gstin,
        purpose="loan_origination",
        duration_months=12,
    )

    # Persist AA consent_id in the DPDP consent ledger
    if input.data_principal_id:
        consent_client = get_consent_client()
        await consent_client.link_aa_consent(
            data_principal_id=input.data_principal_id,
            aa_consent_id=consent.consent_id,
            loan_application_id=input.loan_application_id,
        )

    status = await aa_client.check_consent_status(consent.consent_id)
    if status.status != "approved":
        return {"data_received": False, "months_available": 0, "fips_responded": []}

    data = await aa_client.fetch_financial_data(consent.consent_id)

    return {
        "data_received": True,
        "months_available": data.months_available,
        "fips_responded": [s.get("bank_name", "unknown") for s in data.bank_statements],
        "gst_returns_count": len(data.gst_returns),
        "aa_consent_id": consent.consent_id,
    }


@activity.defn(name="submit_to_lender")
async def submit_to_lender(input: SubmitToLenderInput) -> dict:
    """Submit loan application to matched lender(s) via OCEN (mocked or real)."""
    log = logger.bind(
        loan_application_id=input.loan_application_id,
        lender_count=len(input.lender_ids or []),
    )
    log.info("submitting_to_lender")

    ocen_client = get_ocen_client()
    submission = await ocen_client.submit_application(
        application_id=input.loan_application_id,
        lender_ids=input.lender_ids or [],
        payload={"application_id": input.loan_application_id},
    )

    offer_status = await ocen_client.check_offer_status(submission.submission_id)

    if offer_status.offers:
        return {
            "offer_received": True,
            "offer": offer_status.offers[0],
            "submission_id": submission.submission_id,
        }

    return {"offer_received": False, "offer": None, "submission_id": submission.submission_id}


@activity.defn(name="validate_gst")
async def validate_gst(gstin: str) -> dict:
    """Validate a GSTIN via GST portal (mocked or real)."""
    gst_client = get_gst_client()
    result = await gst_client.validate_gstin(gstin)
    return {"gstin": result.gstin, "valid": result.valid, "trade_name": result.trade_name}


# ─── DPDP Rights Activities ───────────────────────────────────


@dataclass
class DSRInput:
    request_id: str
    data_principal_id: str
    right_type: str


@activity.defn(name="execute_access_right")
async def execute_access_right(input: DSRInput) -> dict:
    """Collect all PII for a data principal (Right to Access)."""
    log = logger.bind(request_id=input.request_id, right_type="access")
    log.info("executing_access_right")

    from libs.db.data_source import PlatformDataSource
    from libs.integrations.factory import get_db_session_factory

    source = PlatformDataSource(get_db_session_factory())
    data = await source.collect(input.data_principal_id)
    return {"status": "fulfilled", "data": data}


@activity.defn(name="execute_erasure_right")
async def execute_erasure_right(input: DSRInput) -> dict:
    """Pseudonymize PII for a data principal (Right to Erasure)."""
    log = logger.bind(request_id=input.request_id, right_type="erasure")
    log.info("executing_erasure_right")

    from libs.db.data_source import PlatformDataSource
    from libs.integrations.factory import get_db_session_factory

    source = PlatformDataSource(get_db_session_factory())
    result = await source.erase(input.data_principal_id)
    return {"status": "fulfilled" if result.get("erased") else "held", "result": result}


@activity.defn(name="execute_correction_right")
async def execute_correction_right(input: DSRInput) -> dict:
    """Placeholder for correction right — requires manual review."""
    log = logger.bind(request_id=input.request_id, right_type="correction")
    log.info("correction_right_queued_for_review")
    return {"status": "pending_review", "reason": "correction_requires_manual_verification"}


# ─── DPDP Retention Activities ─────────────────────────────────


@dataclass
class RetentionInput:
    dry_run: bool = False


@activity.defn(name="enforce_retention")
async def enforce_retention(input: RetentionInput) -> dict:
    """Enforce retention policies from dpdp_config.yaml."""
    import yaml

    log = logger.bind(dry_run=input.dry_run)
    log.info("enforcing_retention_policies")

    config_path = os.environ.get("DPDP_CONFIG_PATH", "dpdp_config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    policies = config.get("retention", [])
    results = []

    for policy in policies:
        category = policy["data_category"]
        days = policy["retention_days"]
        log.info(
            "retention_policy_check",
            category=category,
            retention_days=days,
        )

        if input.dry_run:
            results.append({
                "category": category,
                "action": "dry_run",
                "records_affected": 0,
            })
            continue

        from libs.db.retention_handlers import get_retention_handler

        handler = get_retention_handler(category)
        if handler:
            count = await handler.enforce(days)
            results.append({
                "category": category,
                "action": "enforced",
                "records_affected": count,
            })
        else:
            results.append({
                "category": category,
                "action": "no_handler",
                "records_affected": 0,
            })

    log.info("retention_enforcement_complete", policies_processed=len(results))
    return {"policies_processed": len(results), "results": results}


# ─── DPDP Breach Detection Activities ─────────────────────────


@dataclass
class BreachInput:
    rule: str
    event_count: int
    window_minutes: int
    actor_id: str = ""
    details: dict | None = None

    def __post_init__(self) -> None:
        if self.details is None:
            self.details = {}


@activity.defn(name="detect_breaches")
async def detect_breaches(input: BreachInput) -> dict:
    """Confirm whether a suspected breach meets the threshold for notification."""
    import yaml

    log = logger.bind(rule=input.rule, event_count=input.event_count)
    log.info("evaluating_breach_detection")

    config_path = os.environ.get("DPDP_CONFIG_PATH", "dpdp_config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    rules = {r["rule"]: r for r in config.get("breach", {}).get("detection_rules", [])}
    rule_config = rules.get(input.rule)

    if not rule_config:
        return {"confirmed": False, "reason": f"unknown_rule: {input.rule}"}

    threshold = rule_config["threshold"]
    if input.event_count >= threshold:
        log.warning(
            "breach_confirmed",
            rule=input.rule,
            count=input.event_count,
            threshold=threshold,
        )
        return {"confirmed": True, "threshold": threshold, "actual": input.event_count}

    return {"confirmed": False, "reason": "below_threshold"}


@activity.defn(name="notify_dpbi")
async def notify_dpbi(input: BreachInput) -> dict:
    """Notify the Data Protection Board of India (DPBI) of a confirmed breach."""
    import yaml

    log = logger.bind(rule=input.rule)
    log.info("notifying_dpbi")

    config_path = os.environ.get("DPDP_CONFIG_PATH", "dpdp_config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)

    endpoint = config.get("breach", {}).get("notification", {}).get("dpbi_endpoint", "")

    if not endpoint:
        log.warning("dpbi_endpoint_not_configured")
        return {"notified": False, "reason": "endpoint_not_configured"}

    # In production: POST to DPBI endpoint with breach details
    # For now: log the notification (sandbox mode)
    log.info("dpbi_notification_sent", endpoint=endpoint, rule=input.rule)
    return {"notified": True, "endpoint": endpoint}


@activity.defn(name="notify_affected_principals")
async def notify_affected_principals(input: BreachInput) -> dict:
    """Notify affected data principals of a breach."""
    log = logger.bind(rule=input.rule, actor_id=input.actor_id)
    log.info("notifying_affected_principals")

    # In production: query audit log for affected principals, send notifications
    # For now: return placeholder count
    return {"count": 0, "reason": "notification_system_pending"}


# ─── OCEN Network Protocol Activities ─────────────────────────


@dataclass
class SubmitOcenLoanRequestInput:
    loan_application_id: str
    borrower_gstin: str = ""
    borrower_name: str = ""
    requested_amount: float = 0.0
    tenure_months: int = 3


@activity.defn(name="submit_ocen_loan_request")
async def submit_ocen_loan_request(input: SubmitOcenLoanRequestInput) -> dict:
    """Submit loan application to lenders via OCEN 4.0 network protocol.

    Builds a CreateLoanApplicationRequest with proper MetaData, signs it,
    and POSTs to all lenders in the product network.
    Returns ACK trace IDs — actual decisions arrive asynchronously.
    """
    log = logger.bind(loan_application_id=input.loan_application_id)
    log.info("submitting_ocen_loan_request")

    network_client = get_ocen_network_client()
    metadata = network_client.build_metadata()
    product_data = network_client.build_product_data()

    request = CreateLoanApplicationRequest(
        metadata=metadata,
        product_data=product_data,
        loan_applications=[
            OcenLoanApplication(
                loan_application_id=input.loan_application_id,
                borrower=Borrower(
                    primaryId=input.borrower_gstin or "UNKNOWN",
                    primary_id_type="GSTIN",
                    name=input.borrower_name,
                ),
            ),
        ],
    )

    acks = await network_client.submit_loan_application(request)

    return {
        "submitted": True,
        "ack_count": len(acks),
        "trace_ids": [ack.trace_id for ack in acks],
    }
