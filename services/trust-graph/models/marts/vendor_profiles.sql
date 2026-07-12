-- Mart: Vendor profiles aggregated across all anchors

with trust as (
    select * from {{ ref('trust_scores') }}
),

attestations as (
    select
        vendor_gstin,
        count(*) as total_attestations,
        count(case when is_kind1 then 1 end) as kind1_attestations
    from {{ ref('stg_trade_events') }}
    where event_type = 'INVOICE_KIND1_ATTESTED'
    group by vendor_gstin
)

select
    t.vendor_gstin,
    count(distinct t.anchor_gstin) as anchor_count,
    sum(t.total_loans) as lifetime_loans,
    sum(t.repaid_loans) as lifetime_repaid,
    sum(t.total_disbursed) as lifetime_disbursed,
    avg(t.trust_score) as avg_trust_score,
    max(t.trust_score) as max_trust_score,
    min(t.first_loan_at) as first_ever_loan,
    max(t.latest_loan_at) as most_recent_loan,
    coalesce(a.total_attestations, 0) as total_attestations,
    coalesce(a.kind1_attestations, 0) as kind1_attestations
from trust t
left join attestations a on t.vendor_gstin = a.vendor_gstin
group by t.vendor_gstin, a.total_attestations, a.kind1_attestations
