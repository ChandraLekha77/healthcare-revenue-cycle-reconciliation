# Business Requirements Document

## 1. Document purpose

This document defines the initial business requirements for a healthcare
revenue-cycle reconciliation and analytics system built from synthetic Synthea
records and public CMS reference data. It establishes the questions, scope,
users, controls, and limitations that subsequent implementation work must
honor.

Synthea records and financial values are synthetic. Nothing in this project
represents actual patients, an actual provider organization, contractual payer
terms, or real financial performance.

## 2. Business problem

Revenue-cycle data is distributed across encounters, claims, claim
transactions, clinical codes, and payer records. Without consistent linkage and
validation, analysts cannot reliably determine whether:

- every eligible encounter has a claim;
- every claim resolves to its encounter, patient, payer, and transactions;
- payments, adjustments, transfers, and outstanding balances reconcile;
- duplicate claim records or invalid code references exist;
- receivables are outstanding and how long they have remained outstanding; or
- potential underpayment and revenue-leakage indicators warrant review.

The project must create a traceable analytical layer that identifies these
conditions without asserting unsupported causality, contractual entitlement, or
real-world financial impact.

## 3. Intended users

| User group | Intended use |
| --- | --- |
| Revenue-cycle analysts | Review encounter, claim, payment, adjustment, balance, and exception detail. |
| Finance analysts | Monitor synthetic charges, payments, outstanding balances, aging, and provisional leakage indicators. |
| Coding and data-quality analysts | Review diagnosis and procedure-code validity against versioned references. |
| Data engineers | Operate ingestion, validation, transformations, tests, and lineage. |
| Analytics engineers | Maintain dbt models, documented business logic, and reproducible metrics. |
| Reporting consumers | Review aggregated trends and drill into supported exceptions in Power BI. |

The system is an analytical and data-quality tool. It is not a clinical system,
claims adjudication engine, accounting subledger, or contractual reimbursement
system.

## 4. Objectives

1. Preserve raw Synthea and CMS source files with version and checksum metadata.
2. Load source data into a controlled PostgreSQL raw layer without changing the
   original files.
3. Standardize types, identifiers, code formats, and timestamps in staging.
4. Build defensible patient, encounter, claim, transaction, and payer
   relationships using source identifiers.
5. Reconcile claim charges, payments, adjustments, transfers, and outstanding
   amounts at the lowest supported grain.
6. Identify missing, duplicate, invalid, or unmatched records without silently
   discarding them.
7. Produce documented finance and reconciliation facts with traceable lineage.
8. Present aggregate KPIs and exception detail without overstating synthetic or
   reference data.

## 5. Scope

### 5.1 In scope

- Version-pinned acquisition and validation of selected Synthea CSV files.
- Version-pinned acquisition and validation of selected CMS ICD-10-CM, HCPCS
  Level II, and Medicare Physician Fee Schedule reference files.
- PostgreSQL `raw`, `staging`, and `analytics` schemas.
- Staging of patients, encounters, procedures, medications, conditions, claims,
  claim transactions, and payers.
- Core patient, payer, procedure, encounter, claim, and transaction models.
- Identifier-based encounter-to-claim and claim-to-transaction matching.
- Diagnosis and procedure-code reference validation using the version applicable
  to the event or service date when available.
- Exception facts for unbilled encounters, duplicate claims, code mismatches,
  reconciliation differences, outstanding receivables, aging, denials,
  provisional underpayments, and provisional revenue leakage.
- Documented KPIs and Power BI-ready analytical outputs.
- Automated tests for keys, relationships, accepted values, amounts, and
  reconciliation controls.

### 5.2 Out of scope

- Production protected health information or real patient records.
- Submission, adjudication, correction, or resubmission of claims.
- General-ledger posting, cash application, bank reconciliation, or audit
  certification.
- Real payer contracts, fee schedules, coverage policies, or negotiated rates.
- Comprehensive licensed CPT content or redistribution of AMA-owned content.
- Medical-necessity, clinical appropriateness, fraud, or compliance decisions.
- Predictive denial, reimbursement, or collections models.
- Automatic write-back to source, billing, EHR, payer, or financial systems.

## 6. Business questions

The analytical system should answer the following questions when the required
source fields are available:

### Encounter and claim completeness

1. How many encounters have at least one defensibly linked claim?
2. Which encounters have no linked claim and are therefore flagged as
   potentially unbilled?
3. Which claims cannot be linked to an encounter or patient using documented
   identifiers?
4. Are multiple claim records present for the same source claim identifier?

### Claim and transaction reconciliation

5. Which claims have charges but no associated financial transactions?
6. Do charge, payment, adjustment, transfer, and outstanding transaction amounts
   reconcile at claim and charge-line grain?
7. Which transaction records reference missing claims, patients, providers, or
   code values?
8. What amount remains outstanding by claim, payer, service date, and aging
   bucket?

### Coding quality

9. Are diagnosis codes valid in the selected ICD-10-CM reference version for the
   relevant service date?
10. Are procedure codes present in the applicable HCPCS or MPFS reference?
11. Which codes cannot be validated because the source omits a code-system
    identifier or the applicable reference version is unavailable?

### Financial monitoring

12. What are the synthetic gross charges, payments, adjustments, transfers, and
    outstanding balances for the selected period?
13. What is the distribution of outstanding balances across documented aging
    buckets?
14. Which records meet the documented, source-supported denial criteria?
15. Which records are potential underpayment candidates under an explicitly
    approved comparison basis?
16. Which identified exceptions contribute to provisional revenue-leakage
    indicators, without double counting?

## 7. Functional requirements

| ID | Requirement |
| --- | --- |
| FR-01 | Preserve raw files byte-for-byte and record source URL, version, size, checksum, and acquisition timestamp. |
| FR-02 | Fail ingestion when required files or headers are missing or structurally invalid. |
| FR-03 | Retain rejected or unmatched records with a reason; do not silently drop them. |
| FR-04 | Standardize identifiers without altering their semantic value. |
| FR-05 | Use source identifiers and documented relationships for matching; amount equality alone is not a valid match rule. |
| FR-06 | Maintain transaction grain and signed source amounts before aggregation. |
| FR-07 | Keep code-validation status separate from financial reconciliation status. |
| FR-08 | Apply code references by effective date where the source provides sufficient dates and version metadata. |
| FR-09 | Make every KPI traceable to model, grain, numerator, denominator, exclusions, and refresh timestamp. |
| FR-10 | Provide aggregate KPIs with drill-through to supporting records and exception reasons. |
| FR-11 | Execute data-quality and reconciliation tests before publishing analytical outputs. |
| FR-12 | Log source, row-count, load, validation, transformation, and failure events without logging credentials. |

## 8. Non-functional requirements

- **Reliability:** acquisition and load processes must be repeatable and
  idempotent for the same source version.
- **Integrity:** database writes must use transactions where partial loads could
  create inconsistent state.
- **Performance:** large CSVs must be streamed or processed in bounded chunks.
- **Security:** credentials must come from environment variables and must not be
  committed or logged.
- **Maintainability:** configuration, source parsing, database access, business
  logic, and orchestration must remain separated.
- **Observability:** material pipeline stages must emit structured success and
  failure information with counts and durations.
- **Testability:** key relationships and financial calculations must have unit,
  integration, and data-quality tests appropriate to their risk.
- **Auditability:** published facts must retain source identifiers, reference
  versions, and transformation lineage.

## 9. Assumptions

1. Source identifiers are stable within the pinned Synthea generation run.
2. Claims and transactions may contain multiple records per encounter and claim;
   cardinality must be measured before match rules are finalized.
3. Source transaction `TYPE` values will determine financial classification only
   after accepted values and sign behavior are profiled.
4. A blank termination date in a reference file means no termination date was
   supplied in that release, not that the code is valid indefinitely.
5. Service dates drive reference-version selection when available. Where no
   service date exists, validation status must state that the effective version
   could not be determined.
6. All currency-like values in Synthea are synthetic and assumed to use one
   consistent currency because no currency field is supplied.
7. Reporting periods, aging buckets, materiality thresholds, tolerances, and
   denominator rules require explicit approval before production use.

## 10. Data limitations and exclusions

- Synthea data does not provide actual remittance advice, ERA reason codes,
  contractual allowed amounts, payer contract terms, denial reason codes, appeal
  status, deposit dates, or general-ledger entries.
- Claim `STATUS1`, `STATUS2`, and `STATUSP` semantics require confirmation from
  Synthea source documentation before they can define denials.
- The source does not explicitly identify a code system for every diagnosis or
  procedure field. Validation may therefore be `unknown_code_system` rather than
  invalid.
- ICD-10-CM reference files use release-level effective periods rather than
  row-level dates.
- CMS HCPCS Level II does not constitute a comprehensive licensed CPT Level I
  reference.
- MPFS RVUs and payment indicators apply to Medicare PFS policy. They are not
  contractual payer reimbursement amounts and must not automatically determine
  underpayment.
- The selected CMS references are effective on November 23, 2026, while the
  Synthea sample was generated earlier. Historical code validation requires the
  reference version effective on each service date; the current snapshot alone
  is insufficient for all historical records.
- Equal amounts do not prove records belong together. Amounts may be used only
  as secondary reconciliation evidence after identifier-based relationships.

## 11. Acceptance criteria for later implementation

This BRD is satisfied only when later implementation demonstrates that:

1. raw row counts and checksums reconcile to inventories;
2. required keys and relationships are tested at their documented grain;
3. exception facts retain the originating source identifiers and reasons;
4. financial facts reconcile to source transaction totals within an approved
   tolerance;
5. code validation records the reference version and effective-date outcome;
6. KPI results reproduce from documented formulas and exclusions; and
7. known limitations appear in technical and reporting documentation.

## 12. Open decisions

- Approved reporting timezone and currency label.
- Final claim and encounter matching cardinalities after source profiling.
- Approved transaction sign convention and handling of transfers.
- Denial status values and denominator.
- A/R aging anchor date and bucket boundaries.
- Contractual benchmark for underpayment analysis.
- Materiality and reconciliation tolerances.
- Revenue-leakage categories and precedence rules to prevent double counting.
- Historical CMS reference versions required for Synthea service dates.
