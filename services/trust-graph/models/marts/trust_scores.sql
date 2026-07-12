-- Mart: Trust scores per vendor-anchor pair
-- This is the core of the proprietary Trust Graph moat

with loans as (
    select * from {{ ref('stg_loan_applications') }}
),

vendor_anchor_stats as (
    select
        vendor_gstin,
        anchor_gstin,
        count(*) as total_loans,
        count(case when loan_status = 'REPAID' then 1 end) as repaid_loans,
        count(case when loan_status = 'ACTIVE' then 1 end) as active_loans,
        avg(amount) as avg_loan_amount,
        avg(days_to_repay) as avg_days_to_repay,
        min(originated_at) as first_loan_at,
        max(originated_at) as latest_loan_at,
        sum(amount) as total_disbursed
    from loans
    group by vendor_gstin, anchor_gstin
)

select
    vendor_gstin,
    anchor_gstin,
    total_loans,
    repaid_loans,
    active_loans,
    avg_loan_amount,
    avg_days_to_repay,
    first_loan_at,
    latest_loan_at,
    total_disbursed,

    -- Trust score: repayment rate weighted by volume
    case
        when total_loans = 0 then 0
        else round((repaid_loans::numeric / total_loans) * 100, 2)
    end as repayment_rate_pct,

    -- Composite trust score (0-100)
    case
        when total_loans = 0 then 0
        when total_loans < 3 then
            round((repaid_loans::numeric / total_loans) * 50, 0)
        else
            round(
                (repaid_loans::numeric / total_loans) * 70
                + least(total_loans, 20)::numeric / 20 * 20
                + case when avg_days_to_repay <= 30 then 10 else 0 end,
                0
            )
    end as trust_score

from vendor_anchor_stats
