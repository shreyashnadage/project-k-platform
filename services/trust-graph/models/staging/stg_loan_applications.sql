-- Staging model: loan applications with current status

with events as (
    select * from {{ ref('stg_trade_events') }}
),

originated as (
    select
        loan_application_id,
        entity_id as invoice_id,
        vendor_gstin,
        anchor_gstin,
        amount,
        occurred_at as originated_at
    from events
    where event_type = 'LOAN_ORIGINATED'
),

repaid as (
    select
        loan_application_id,
        occurred_at as repaid_at,
        (payload->>'days_to_repay')::int as days_to_repay
    from events
    where event_type = 'REPAYMENT_OBSERVED'
)

select
    o.loan_application_id,
    o.invoice_id,
    o.vendor_gstin,
    o.anchor_gstin,
    o.amount,
    o.originated_at,
    r.repaid_at,
    r.days_to_repay,
    case
        when r.repaid_at is not null then 'REPAID'
        when o.originated_at is not null then 'ACTIVE'
        else 'UNKNOWN'
    end as loan_status
from originated o
left join repaid r on o.loan_application_id = r.loan_application_id
