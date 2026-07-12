-- Staging model: raw trade events from the event stream
-- Source: trade_events table populated by the Redpanda consumer relay

with source as (
    select * from {{ source('raw', 'trade_events') }}
)

select
    event_id,
    event_type,
    entity_type,
    entity_id,
    correlation_id as loan_application_id,
    payload,
    (payload->>'irn')::text as irn,
    (payload->>'ims_status')::text as ims_status,
    (payload->>'repayment_routing_active')::boolean as repayment_routing_active,
    (payload->>'is_kind1')::boolean as is_kind1,
    (payload->>'amount')::numeric as amount,
    (payload->>'anchor_gstin')::text as anchor_gstin,
    (payload->>'vendor_gstin')::text as vendor_gstin,
    occurred_at,
    created_at
from source
