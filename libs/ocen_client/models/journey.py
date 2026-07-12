"""OCEN 4.0 loan journey data models.

These match the OCEN network's CreateLoanApplicationRequest/Response schemas
as defined in the iSPIRT AuthStarter reference implementation.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003
from typing import Any

from pydantic import BaseModel, Field


class MetaData(BaseModel):
    """OCEN request/response metadata — present in every network transaction."""

    version: str = Field(default="4.0.0alpha")
    originator_org_id: str = Field(..., alias="originatorOrgId")
    originator_participant_id: str = Field(..., alias="originatorParticipantId")
    timestamp: str = Field(default="")
    trace_id: str = Field(..., alias="traceId")
    request_id: str = Field(..., alias="requestId")

    model_config = {"populate_by_name": True}


class ProductData(BaseModel):
    """OCEN product network identification."""

    product_id: str = Field(..., alias="productId")
    product_network_id: str = Field(..., alias="productNetworkId")

    model_config = {"populate_by_name": True}


class Document(BaseModel):
    """Pledged or supporting document."""

    source: str = "GSTN"
    source_identifier: str = Field(default="", alias="sourceIdentifier")
    format: str = "JSON"
    reference: str = ""
    type: str = "GST_PROFILE"
    is_data_inline: bool = Field(default=True, alias="isDataInline")
    data: str = ""

    model_config = {"populate_by_name": True}


class Address(BaseModel):
    """Contact address."""

    hba: str = ""
    srl: str = ""
    landmark: str = ""
    als: str = ""
    vtc: str = ""
    pin_code: str = Field(default="", alias="pinCode")
    po: str = ""
    district: str = ""
    state: str = ""
    country: str = "India"

    model_config = {"populate_by_name": True}


class ContactDetail(BaseModel):
    """Borrower/applicant contact information."""

    type: str = "PRIMARY"
    description: str = ""
    phone: str = ""
    email: str = ""
    address: Address | None = None

    model_config = {"populate_by_name": True}


class Borrower(BaseModel):
    """Borrower (vendor) in the OCEN loan application."""

    primary_id: str = Field(..., alias="primaryId")
    primary_id_type: str = Field(default="PAN", alias="primaryIdType")
    name: str = ""
    category: str = "ORGANIZATION"
    contact_details: list[ContactDetail] = Field(default_factory=list, alias="contactDetails")
    additional_identifiers: list[dict[str, Any]] = Field(
        default_factory=list, alias="additionalIdentifiers"
    )
    documents: list[Document] = Field(default_factory=list)
    aa_identifier: str = Field(default="", alias="aaIdentifier")

    model_config = {"populate_by_name": True}


class Duration(BaseModel):
    """Time duration."""

    duration: int = 0
    unit: str = "MONTH"


class Charge(BaseModel):
    """Fee/charge structure."""

    charge_type: str = Field(default="FIXED_AMOUNT", alias="chargeType")
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class LoanTerms(BaseModel):
    """Loan terms and conditions."""

    requested_amount: float = Field(default=0, alias="requestedAmount")
    currency: str = "INR"
    sanctioned_amount: float = Field(default=0, alias="sanctionedAmount")
    net_disbursed_amount: float = Field(default=0, alias="netDisbursedAmount")
    interest_type: str = Field(default="FIXED", alias="interestType")
    interest_rate: float = Field(default=0, alias="interestRate")
    annual_percentage_rate: float = Field(default=0, alias="annualPercentageRate")
    tenure: Duration | None = None
    cooling_off_period: Duration | None = Field(default=None, alias="coolingOffPeriod")
    charges: dict[str, Charge] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class LoanApplication(BaseModel):
    """A single loan application in the OCEN batch."""

    loan_application_id: str = Field(..., alias="loanApplicationId")
    loan_application_status: str = Field(default="CREATED", alias="loanApplicationStatus")
    created_date: date | None = Field(default=None, alias="createdDate")
    borrower: Borrower | None = None
    guarantors: list[Borrower] = Field(default_factory=list)
    applicants: list[Borrower] = Field(default_factory=list)
    pledged_documents: list[Document] = Field(default_factory=list, alias="pledgedDocuments")
    terms: LoanTerms | None = None
    description: str = ""

    model_config = {"populate_by_name": True}


class CreateLoanApplicationRequest(BaseModel):
    """OCEN CreateLoanApplicationRequest — LA sends to Lender.

    Endpoint: POST /v4.0.0alpha/loanApplications/createLoanRequest
    """

    metadata: MetaData
    product_data: ProductData = Field(..., alias="productData")
    loan_applications: list[LoanApplication] = Field(..., alias="loanApplications")

    model_config = {"populate_by_name": True}


class ResponseStatus(BaseModel):
    """Response status in async callback."""

    status: str = "SUCCESS"
    response_detail: str = Field(default="", alias="responseDetail")

    model_config = {"populate_by_name": True}


class CreateLoanApplicationResponse(BaseModel):
    """OCEN CreateLoanApplicationResponse — Lender sends back to LA async.

    Endpoint: POST /v4.0.0alpha/loanApplications/createLoanResponse
    """

    metadata: MetaData
    product_data: ProductData = Field(..., alias="productData")
    response: ResponseStatus
    loan_applications: list[LoanApplication] = Field(..., alias="loanApplications")

    model_config = {"populate_by_name": True}


class OcenAckResponse(BaseModel):
    """Synchronous ACK response for every OCEN network transaction."""

    error: str | None = None
    trace_id: str = Field(..., alias="traceId")
    timestamp: str = ""

    model_config = {"populate_by_name": True}
