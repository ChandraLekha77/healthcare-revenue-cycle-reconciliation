# KPI Definitions

## 1. Purpose and status

This catalog defines the initial reconciliation and financial KPIs implied by
the project plan and planned dbt models. Definitions are intentionally explicit
about grain, source requirements, exclusions, and limitations.

All financial values are synthetic. KPIs marked **provisional** must not be
published as authoritative until the open business rules and source semantics
are approved.

## 2. Shared conventions

- **Reporting period:** based on the documented service, transaction, or aging
  date for the metric; it must be shown with every published value.
- **Claim grain:** the unique source claim identifier unless profiling proves a
  composite key is required.
- **Encounter grain:** the unique source encounter identifier.
- **Transaction grain:** source transaction `ID`; `CHARGEID` identifies a charge
  line within a claim when populated.
- **Distinct counts:** count the documented business key, not physical rows,
  unless the KPI explicitly measures rows.
- **Amounts:** preserve source signs. Classification and sign normalization must
  be tested before aggregation.
- **Unknowns:** records lacking required relationship or status fields remain in
  the population with an explicit unknown status unless the metric definition
  excludes them.
- **Tolerances:** no monetary or percentage tolerance is approved yet. Published
  reconciliation status must expose the applied tolerance.

## 3. Reconciliation KPIs

### 3.1 Encounter-to-claim match rate

| Attribute | Definition |
| --- | --- |
| Business meaning | Share of in-scope encounters with at least one defensibly linked claim. |
| Formula | Distinct matched encounters / distinct eligible encounters. |
| Grain | Encounter, aggregated by reporting dimensions. |
| Planned source | `int_encounter_claim_matching`, `fct_encounters`, `fct_claims`. |
| Exclusions | Encounters explicitly documented as not billable, if such a source field becomes available. No current source field supports this exclusion. |
| Limitation | Final matching keys and eligible population remain subject to relationship profiling. |

### 3.2 Potentially unbilled encounter count

| Attribute | Definition |
| --- | --- |
| Business meaning | Encounters in scope with no linked claim under the approved matching rule. |
| Formula | Count of distinct eligible encounter IDs where matched claim count = 0. |
| Grain | Encounter. |
| Planned source | `fct_unbilled_encounters`. |
| Limitation | `Potentially unbilled` is an exception flag, not proof that billing was required. |

### 3.3 Potentially unbilled encounter rate

| Attribute | Definition |
| --- | --- |
| Business meaning | Share of eligible encounters flagged as potentially unbilled. |
| Formula | Potentially unbilled encounter count / distinct eligible encounters. |
| Zero denominator | Report unavailable, not zero. |

### 3.4 Claim-to-transaction match rate

| Attribute | Definition |
| --- | --- |
| Business meaning | Share of claims with at least one linked claim transaction. |
| Formula | Distinct claims with linked transactions / distinct in-scope claims. |
| Grain | Claim. |
| Planned source | `int_claim_payment_matching`, `fct_claims_transactions`. |
| Limitation | A linked transaction does not by itself mean the claim is financially reconciled. |

### 3.5 Financially reconciled claim rate

| Attribute | Definition |
| --- | --- |
| Business meaning | Share of claims whose classified source components satisfy the approved reconciliation equation within the disclosed tolerance. |
| Provisional equation | Charges - payments - adjustments - transfers - outstanding balance = reconciliation difference. Sign normalization remains to be approved from source profiling. |
| Formula | Distinct reconciled claims / distinct claims with sufficient transaction data. |
| Planned source | `fct_claim_reconciliation`. |
| Limitation | Claims lacking required transaction components are `insufficient_data`, not unreconciled. |

### 3.6 Reconciliation difference

| Attribute | Definition |
| --- | --- |
| Business meaning | Residual amount after applying the approved claim reconciliation equation. |
| Grain | Claim and optionally charge line. |
| Planned source | `fct_claim_reconciliation`. |
| Status | Provisional until transaction signs and transfer behavior are validated. |

### 3.7 Duplicate claim count

| Attribute | Definition |
| --- | --- |
| Business meaning | Number of claim records participating in an approved duplicate group. |
| Primary rule | Exact duplicate source claim identifier is a deterministic duplicate condition. |
| Additional rules | Any composite-content rule requires separate approval and must never use amount equality alone. |
| Planned source | `fct_duplicate_claims`. |

### 3.8 Duplicate claim rate

| Attribute | Definition |
| --- | --- |
| Formula | Distinct duplicated claim identifiers / distinct in-scope claim identifiers. |
| Limitation | Physical duplicate rows and duplicated business claims are separate measures and must not be conflated. |

### 3.9 Code mismatch count and rate

| Attribute | Definition |
| --- | --- |
| Business meaning | Diagnosis or procedure references that fail the applicable validation outcome. |
| Count | Distinct source code occurrences with `validation_status = invalid`. |
| Rate | Invalid code occurrences / code occurrences with a known system and applicable reference version. |
| Planned source | `int_claim_code_validation`, `fct_code_mismatches`. |
| Exclusions | `unknown_code_system`, `reference_version_unavailable`, and blank optional codes are reported separately, not counted invalid. |

## 4. Financial KPIs

### 4.1 Gross charges

| Attribute | Definition |
| --- | --- |
| Business meaning | Sum of source transactions classified as charge activity. |
| Formula | Sum of signed or normalized `AMOUNT` for approved charge transaction types. |
| Grain | Transaction, aggregated by service period and dimensions. |
| Planned source | `fct_financial_transactions`. |
| Limitation | Transaction type values and sign behavior must be profiled before finalization. |

### 4.2 Payments

| Attribute | Definition |
| --- | --- |
| Business meaning | Sum of source transactions classified as payments. |
| Formula | Sum of approved payment transaction amounts using the documented sign convention. |
| Limitation | The source does not provide deposit reconciliation or general-ledger confirmation. |

### 4.3 Adjustments

| Attribute | Definition |
| --- | --- |
| Business meaning | Sum of source transactions classified as adjustments. |
| Limitation | The source does not provide standard adjustment reason codes; contractual, administrative, and write-off categories cannot be inferred. |

### 4.4 Transfers

| Attribute | Definition |
| --- | --- |
| Business meaning | Sum of transfer activity classified from transaction type and transfer fields. |
| Limitation | Transfer-in and transfer-out netting rules require source profiling and approval. |

### 4.5 Outstanding accounts receivable

| Attribute | Definition |
| --- | --- |
| Business meaning | Synthetic amount remaining outstanding at the selected as-of date. |
| Preferred source | Transaction `OUTSTANDING` at the lowest supported charge/claim grain, reconciled against claim outstanding fields. |
| Planned source | `fct_accounts_receivable`. |
| Limitation | The source is not an accounting subledger and does not provide a historical balance snapshot series. |

### 4.6 A/R aging distribution

| Attribute | Definition |
| --- | --- |
| Business meaning | Outstanding A/R grouped by elapsed days from an approved anchor date to an as-of date. |
| Formula | As-of date - approved aging anchor date. |
| Planned source | `fct_ar_aging`. |
| Status | Provisional. Anchor date and bucket boundaries are open decisions. |
| Required disclosure | Show the as-of date, anchor date, bucket boundaries, unknown-date amount, and negative-balance handling. |

### 4.7 Denial count, amount, and rate

| Attribute | Definition |
| --- | --- |
| Business meaning | Claims meeting an approved denial-status definition. |
| Count | Distinct denied claims. |
| Amount | Approved denied amount basis, stated explicitly. |
| Rate | Distinct denied claims / distinct adjudicated claims. |
| Planned source | `fct_denials`. |
| Status | Provisional because source status semantics and denial reasons are not yet documented. |

### 4.8 Potential underpayment amount and rate

| Attribute | Definition |
| --- | --- |
| Business meaning | Difference between actual eligible payment and an approved contractual expected amount when actual is lower beyond an approved tolerance. |
| Amount | Maximum of approved expected amount - eligible actual payment - approved tolerance, and zero. |
| Rate | Distinct underpayment candidates / distinct claims with a valid contractual benchmark. |
| Planned source | `fct_underpayments`. |
| Status | Unavailable with current sources. No payer contract or contractual allowed amount is present. |
| Prohibition | CMS MPFS values must not automatically be used as payer contractual reimbursement. |

### 4.9 Provisional revenue leakage amount

| Attribute | Definition |
| --- | --- |
| Business meaning | Sum of approved, non-overlapping financial exception categories that represent measurable synthetic value at risk. |
| Planned source | `fct_revenue_leakage`. |
| Status | Provisional. Categories, precedence, and amount bases require approval. |
| Required control | Each source record may contribute to a category only under documented precedence rules; total leakage must expose category subtotals and excluded overlaps. |
| Prohibition | Counts of unbilled encounters, code mismatches, or duplicate claims must not be converted to dollars without a source-supported amount basis. |

### 4.10 Net collection rate

| Attribute | Definition |
| --- | --- |
| Business meaning | Payments collected relative to charges after approved contractual adjustments. |
| Typical formula | Payments / (gross charges - contractual adjustments). |
| Status | Unavailable with current sources because contractual adjustments cannot be reliably distinguished from other adjustments. |
| Reporting rule | Do not publish a substituted collection rate under this name. |

## 5. Publication controls

Every published KPI must include:

- metric name and version;
- reporting and as-of dates;
- grain and distinct key;
- numerator and denominator;
- amount sign convention;
- exclusions and unknown population;
- applied tolerance or bucket rule;
- source/reference version;
- refresh timestamp; and
- provisional or approved status.

No KPI should default missing inputs to zero or suppress failed prerequisites.
