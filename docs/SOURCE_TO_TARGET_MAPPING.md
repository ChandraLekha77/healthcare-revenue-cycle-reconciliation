# Source-to-Target Mapping

## 1. Purpose and implementation status

This document maps every selected source field to its intended analytical target. It is a design contract, not evidence that the target tables or dbt models have been implemented. Existing planned dbt filenames are used where available; CMS reference staging targets are logical planned tables and do not yet have model files.

## 2. Mapping conventions

- Raw database tables retain source column names and values plus load metadata.
- Staging fields use snake case and explicit types; invalid parses remain traceable as rejects or quality flags.
- Source identifiers remain text even when they appear numeric.
- Blank and missing values are not converted to zero.
- Synthetic monetary values use an appropriate fixed-point numeric type after profiling.
- All accepted rows should carry `source_filename`, `source_version`, `source_sha256`, `load_id`, and `loaded_at_utc`.
- CMS reference rows should also carry `reference_effective_start` and `reference_effective_end`.
- Intended targets below do not authorize unsupported joins, code-system assumptions, denial rules, reimbursement rules, or financial classifications.

## 3. Planned layer routing

| Source family | Raw target | Staging/normalized target | Primary downstream targets |
| --- | --- | --- | --- |
| Synthea CSV | `raw.synthea_<dataset>` | Existing `stg_*.sql` models | Core, reconciliation, and finance models |
| CMS ICD-10-CM | `raw.cms_icd10cm_fy2027` | Planned `staging.stg_cms_icd10cm` | `int_claim_code_validation` |
| CMS HCPCS Level II | `raw.cms_hcpcs_2026_q4` | Planned `staging.stg_cms_hcpcs` | `int_claim_code_validation`, procedure reference |
| CMS MPFS RVU26D | `raw.cms_mpfs_rvu26d` | Planned `staging.stg_cms_mpfs` | Procedure reference and explicitly approved Medicare analyses only |

## 4. Synthea source mappings

### 4.1 `patients.csv`

- Raw target: `raw.synthea_patients`
- Staging target: `stg_patients`
- Intended downstream: `dim_patients`

| Source field | Intended staging field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| `Id` | `patient_id` | text; trim; required | Primary patient identifier. |
| `BIRTHDATE` | `birth_date` | date | Patient dimension attribute. |
| `DEATHDATE` | `death_date` | date; nullable | Blank does not mean alive beyond dataset cutoff without a defined cutoff. |
| `SSN` | `ssn` | text; nullable | Synthetic sensitive identifier; restrict reporting. |
| `DRIVERS` | `drivers_license` | text; nullable | Synthetic identifier. |
| `PASSPORT` | `passport_number` | text; nullable | Synthetic identifier. |
| `PREFIX` | `name_prefix` | text; nullable | Patient name attribute. |
| `FIRST` | `first_name` | text | Synthetic name. |
| `LAST` | `last_name` | text | Synthetic name. |
| `SUFFIX` | `name_suffix` | text; nullable | Patient name attribute. |
| `MAIDEN` | `maiden_name` | text; nullable | Patient name attribute. |
| `MARITAL` | `marital_status` | text; nullable | Retain source value; accepted values require profiling. |
| `RACE` | `race` | text; nullable | Retain source category. |
| `ETHNICITY` | `ethnicity` | text; nullable | Retain source category. |
| `GENDER` | `gender` | text; nullable | Retain source value; do not infer. |
| `BIRTHPLACE` | `birthplace` | text; nullable | Demographic attribute. |
| `ADDRESS` | `address` | text; nullable | Synthetic address; restrict reporting. |
| `CITY` | `city` | text; nullable | Geography. |
| `STATE` | `state` | text; nullable | Geography. |
| `COUNTY` | `county` | text; nullable | Geography. |
| `ZIP` | `postal_code` | text; nullable; preserve leading zeros | Geography. |
| `LAT` | `latitude` | numeric; nullable; range test | Geography. |
| `LON` | `longitude` | numeric; nullable; range test | Geography. |
| `HEALTHCARE_EXPENSES` | `healthcare_expenses` | numeric; nullable | Synthetic cumulative patient value; not claim charges. |
| `HEALTHCARE_COVERAGE` | `healthcare_coverage` | numeric; nullable | Synthetic cumulative coverage; not contractual allowed amount. |

### 4.2 `encounters.csv`

- Raw target: `raw.synthea_encounters`
- Staging target: `stg_encounters`
- Intended downstream: `fct_encounters`

| Source field | Intended staging field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| `Id` | `encounter_id` | text; trim; required | Primary encounter identifier. |
| `START` | `encounter_start_at` | timestamp with offset | Service timing. |
| `STOP` | `encounter_stop_at` | timestamp with offset; nullable | Validate stop >= start. |
| `PATIENT` | `patient_id` | text; required | Relationship to dim_patients. |
| `ORGANIZATION` | `organization_id` | text; nullable | No organization source table selected; retain as degenerate identifier. |
| `PROVIDER` | `provider_id` | text; nullable | No provider source table selected; retain as degenerate identifier. |
| `PAYER` | `payer_id` | text; nullable | Relationship to dim_payers. |
| `ENCOUNTERCLASS` | `encounter_class` | text; nullable | Retain source category. |
| `CODE` | `encounter_code` | text; nullable | Code system not explicitly supplied. |
| `DESCRIPTION` | `encounter_description` | text; nullable | Source description. |
| `BASE_ENCOUNTER_COST` | `base_encounter_cost` | numeric; nullable | Synthetic amount. |
| `TOTAL_CLAIM_COST` | `total_claim_cost` | numeric; nullable | Encounter-level synthetic amount; not a claim join key. |
| `PAYER_COVERAGE` | `payer_coverage` | numeric; nullable | Synthetic amount; not contractual reimbursement. |
| `REASONCODE` | `reason_code` | text; nullable | Code system not explicitly supplied. |
| `REASONDESCRIPTION` | `reason_description` | text; nullable | Source description. |

### 4.3 `procedures.csv`

- Raw target: `raw.synthea_procedures`
- Staging target: `stg_procedures`
- Intended downstream: `dim_procedures and encounter procedure bridge`

| Source field | Intended staging field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| `START` | `procedure_start_at` | timestamp with offset | Event time. |
| `STOP` | `procedure_stop_at` | timestamp with offset; nullable | Validate stop >= start. |
| `PATIENT` | `patient_id` | text; required | Patient relationship. |
| `ENCOUNTER` | `encounter_id` | text; required | Encounter relationship. |
| `CODE` | `procedure_code` | text; required | Validate only after code system/reference basis is established. |
| `DESCRIPTION` | `procedure_description` | text; nullable | Source description; not authoritative reference text. |
| `BASE_COST` | `base_cost` | numeric; nullable | Synthetic amount; not MPFS expected reimbursement. |
| `REASONCODE` | `reason_code` | text; nullable | Code system not explicitly supplied. |
| `REASONDESCRIPTION` | `reason_description` | text; nullable | Source description. |

### 4.4 `medications.csv`

- Raw target: `raw.synthea_medications`
- Staging target: `stg_medications`
- Intended downstream: `staging only in current model plan`

| Source field | Intended staging field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| `START` | `medication_start_at` | timestamp with offset | Medication event time. |
| `STOP` | `medication_stop_at` | timestamp with offset; nullable | Validate stop >= start. |
| `PATIENT` | `patient_id` | text; required | Patient relationship. |
| `PAYER` | `payer_id` | text; nullable | Payer relationship. |
| `ENCOUNTER` | `encounter_id` | text; required | Encounter relationship. |
| `CODE` | `medication_code` | text; required | Code system not explicitly supplied. |
| `DESCRIPTION` | `medication_description` | text; nullable | Source description. |
| `BASE_COST` | `base_cost` | numeric; nullable | Synthetic unit/base amount. |
| `PAYER_COVERAGE` | `payer_coverage` | numeric; nullable | Synthetic amount. |
| `DISPENSES` | `dispenses` | integer; nullable | Validate nonnegative. |
| `TOTALCOST` | `total_cost` | numeric; nullable | Synthetic amount; formula must be profiled, not assumed. |
| `REASONCODE` | `reason_code` | text; nullable | Code system not explicitly supplied. |
| `REASONDESCRIPTION` | `reason_description` | text; nullable | Source description. |

### 4.5 `conditions.csv`

- Raw target: `raw.synthea_conditions`
- Staging target: `stg_conditions`
- Intended downstream: `int_claim_code_validation reference support`

| Source field | Intended staging field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| `START` | `condition_start_at` | timestamp with offset | Condition timing. |
| `STOP` | `condition_stop_at` | timestamp with offset; nullable | Blank may indicate active in source; do not invent end date. |
| `PATIENT` | `patient_id` | text; required | Patient relationship. |
| `ENCOUNTER` | `encounter_id` | text; required | Encounter relationship. |
| `CODE` | `condition_code` | text; required | Code system not explicit; ICD validation may be unknown. |
| `DESCRIPTION` | `condition_description` | text; nullable | Source description. |

### 4.6 `claims.csv`

- Raw target: `raw.synthea_claims`
- Staging target: `stg_claims`
- Intended downstream: `fct_claims`

| Source field | Intended staging field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| `Id` | `claim_id` | text; trim; required | Claim business key pending uniqueness test. |
| `PATIENTID` | `patient_id` | text; required | Patient relationship. |
| `PROVIDERID` | `provider_id` | text; nullable | Degenerate provider identifier. |
| `PRIMARYPATIENTINSURANCEID` | `primary_patient_insurance_id` | text; nullable | Insurance/member reference; does not directly equal payer ID without evidence. |
| `SECONDARYPATIENTINSURANCEID` | `secondary_patient_insurance_id` | text; nullable | Secondary insurance/member reference. |
| `DEPARTMENTID` | `department_id` | text; nullable | Department identifier. |
| `PATIENTDEPARTMENTID` | `patient_department_id` | text; nullable | Patient-department identifier. |
| `DIAGNOSIS1` | `diagnosis_1_code` | text; nullable | Positional diagnosis; code system and version must be determined before validation. |
| `DIAGNOSIS2` | `diagnosis_2_code` | text; nullable | Positional diagnosis; code system and version must be determined before validation. |
| `DIAGNOSIS3` | `diagnosis_3_code` | text; nullable | Positional diagnosis; code system and version must be determined before validation. |
| `DIAGNOSIS4` | `diagnosis_4_code` | text; nullable | Positional diagnosis; code system and version must be determined before validation. |
| `DIAGNOSIS5` | `diagnosis_5_code` | text; nullable | Positional diagnosis; code system and version must be determined before validation. |
| `DIAGNOSIS6` | `diagnosis_6_code` | text; nullable | Positional diagnosis; code system and version must be determined before validation. |
| `DIAGNOSIS7` | `diagnosis_7_code` | text; nullable | Positional diagnosis; code system and version must be determined before validation. |
| `DIAGNOSIS8` | `diagnosis_8_code` | text; nullable | Positional diagnosis; code system and version must be determined before validation. |
| `REFERRINGPROVIDERID` | `referring_provider_id` | text; nullable | Provider reference. |
| `APPOINTMENTID` | `appointment_id` | text; nullable | Candidate relationship evidence; encounters source has no appointment ID. |
| `CURRENTILLNESSDATE` | `current_illness_at` | timestamp/date; nullable | Parse actual source format. |
| `SERVICEDATE` | `service_at` | timestamp/date; required for time-based analysis | Reference-version selection and claim reporting date. |
| `SUPERVISINGPROVIDERID` | `supervising_provider_id` | text; nullable | Provider reference. |
| `STATUS1` | `status_1` | text; nullable | Semantics require source documentation; not yet a denial rule. |
| `STATUS2` | `status_2` | text; nullable | Semantics require source documentation; not yet a denial rule. |
| `STATUSP` | `status_patient` | text; nullable | Semantics require source documentation. |
| `OUTSTANDING1` | `outstanding_1` | numeric; nullable | Meaning/party requires source documentation; reconcile to transactions. |
| `OUTSTANDING2` | `outstanding_2` | numeric; nullable | Meaning/party requires source documentation; reconcile to transactions. |
| `OUTSTANDINGP` | `outstanding_patient` | numeric; nullable | Patient outstanding component; reconcile to transactions. |
| `LASTBILLEDDATE1` | `last_billed_at_1` | timestamp/date; nullable | Candidate aging/billing date; semantics require confirmation. |
| `LASTBILLEDDATE2` | `last_billed_at_2` | timestamp/date; nullable | Candidate aging/billing date; semantics require confirmation. |
| `LASTBILLEDDATEP` | `last_billed_at_patient` | timestamp/date; nullable | Candidate patient billing date. |
| `HEALTHCARECLAIMTYPEID1` | `healthcare_claim_type_id_1` | text; nullable | Retain source classification. |
| `HEALTHCARECLAIMTYPEID2` | `healthcare_claim_type_id_2` | text; nullable | Retain source classification. |

### 4.7 `claims_transactions.csv`

- Raw target: `raw.synthea_claims_transactions`
- Staging target: `stg_claims_transactions`
- Intended downstream: `fct_claims_transactions and fct_financial_transactions`

| Source field | Intended staging field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| `ID` | `transaction_id` | text; required | Transaction business key pending uniqueness test. |
| `CLAIMID` | `claim_id` | text; required | Direct claim relationship. |
| `CHARGEID` | `charge_id` | text; nullable | Charge-line identifier; assess uniqueness within claim. |
| `PATIENTID` | `patient_id` | text; required | Patient relationship. |
| `TYPE` | `transaction_type` | text; required | Controls classification only after accepted values/signs are profiled. |
| `AMOUNT` | `amount` | numeric; nullable | Preserve source sign. |
| `METHOD` | `method` | text; nullable | Payment/adjustment method when supplied. |
| `FROMDATE` | `from_at` | timestamp/date; nullable | Transaction/service timing. |
| `TODATE` | `to_at` | timestamp/date; nullable | Validate to >= from. |
| `PLACEOFSERVICE` | `place_of_service` | text; nullable | Source may contain organization identifier rather than standard POS code; profile first. |
| `PROCEDURECODE` | `procedure_code` | text; nullable | Code-system-aware validation required. |
| `MODIFIER1` | `modifier_1` | text; nullable | Procedure modifier. |
| `MODIFIER2` | `modifier_2` | text; nullable | Procedure modifier. |
| `DIAGNOSISREF1` | `diagnosis_reference_1` | text; nullable | Reference position semantics require source documentation; do not assume it contains a diagnosis code. |
| `DIAGNOSISREF2` | `diagnosis_reference_2` | text; nullable | Reference position semantics require source documentation; do not assume it contains a diagnosis code. |
| `DIAGNOSISREF3` | `diagnosis_reference_3` | text; nullable | Reference position semantics require source documentation; do not assume it contains a diagnosis code. |
| `DIAGNOSISREF4` | `diagnosis_reference_4` | text; nullable | Reference position semantics require source documentation; do not assume it contains a diagnosis code. |
| `UNITS` | `units` | numeric/integer; nullable | Validate nonnegative when applicable. |
| `DEPARTMENTID` | `department_id` | text; nullable | Department identifier. |
| `NOTES` | `notes` | text; nullable | Source note; exclude from aggregate metrics. |
| `UNITAMOUNT` | `unit_amount` | numeric; nullable | Preserve source sign; compare with amount/units only after profiling. |
| `TRANSFEROUTID` | `transfer_out_id` | text; nullable | Candidate transfer relationship. |
| `TRANSFERTYPE` | `transfer_type` | text; nullable | Transfer classification. |
| `PAYMENTS` | `payments_component` | numeric; nullable | Source component; reconcile but avoid double counting AMOUNT. |
| `ADJUSTMENTS` | `adjustments_component` | numeric; nullable | Source component; reconcile but avoid double counting AMOUNT. |
| `TRANSFERS` | `transfers_component` | numeric; nullable | Source component; reconcile but avoid double counting AMOUNT. |
| `OUTSTANDING` | `outstanding_component` | numeric; nullable | Source outstanding component. |
| `APPOINTMENTID` | `appointment_id` | text; nullable | Candidate evidence; encounter source has no appointment ID. |
| `LINENOTE` | `line_note` | text; nullable | Source note. |
| `PATIENTINSURANCEID` | `patient_insurance_id` | text; nullable | Insurance/member reference. |
| `FEESCHEDULEID` | `fee_schedule_id` | text; nullable | Source reference only; no corresponding contract table selected. |
| `PROVIDERID` | `provider_id` | text; nullable | Provider reference. |
| `SUPERVISINGPROVIDERID` | `supervising_provider_id` | text; nullable | Provider reference. |

### 4.8 `payers.csv`

- Raw target: `raw.synthea_payers`
- Staging target: `stg_payers`
- Intended downstream: `dim_payers`

| Source field | Intended staging field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| `Id` | `payer_id` | text; required | Payer key. |
| `NAME` | `payer_name` | text; required | Payer name. |
| `ADDRESS` | `address` | text; nullable | Source address. |
| `CITY` | `city` | text; nullable | Geography. |
| `STATE_HEADQUARTERED` | `state_headquartered` | text; nullable | Geography. |
| `ZIP` | `postal_code` | text; nullable; preserve leading zeros | Geography. |
| `PHONE` | `phone` | text; nullable | Contact attribute. |
| `AMOUNT_COVERED` | `source_amount_covered` | numeric; nullable | Synthetic source aggregate; not claim-level payment. |
| `AMOUNT_UNCOVERED` | `source_amount_uncovered` | numeric; nullable | Synthetic source aggregate. |
| `REVENUE` | `source_revenue` | numeric; nullable | Synthetic payer aggregate; not provider revenue. |
| `COVERED_ENCOUNTERS` | `covered_encounters` | integer; nullable | Source aggregate. |
| `UNCOVERED_ENCOUNTERS` | `uncovered_encounters` | integer; nullable | Source aggregate. |
| `COVERED_MEDICATIONS` | `covered_medications` | integer; nullable | Source aggregate. |
| `UNCOVERED_MEDICATIONS` | `uncovered_medications` | integer; nullable | Source aggregate. |
| `COVERED_PROCEDURES` | `covered_procedures` | integer; nullable | Source aggregate. |
| `UNCOVERED_PROCEDURES` | `uncovered_procedures` | integer; nullable | Source aggregate. |
| `COVERED_IMMUNIZATIONS` | `covered_immunizations` | integer; nullable | Source aggregate. |
| `UNCOVERED_IMMUNIZATIONS` | `uncovered_immunizations` | integer; nullable | Source aggregate. |
| `UNIQUE_CUSTOMERS` | `unique_customers` | integer; nullable | Source aggregate. |
| `QOLS_AVG` | `quality_of_life_score_average` | numeric; nullable | Synthetic source aggregate; not a revenue KPI. |
| `MEMBER_MONTHS` | `member_months` | integer; nullable | Source aggregate. |

## 5. CMS ICD-10-CM mapping

Source member: `Code Descriptions/icd10cm_codes_2027.txt`. The file is headerless fixed-width text. Effective dates come from the FY 2027 release metadata, not individual rows.

| Source element | Intended staging field | Transform | Use or limitation |
| --- | --- | --- | --- |
| Characters 1-7 | `diagnosis_code_compact` | Trim text; required | ICD-10-CM code without display decimal. |
| Character 9 onward | `diagnosis_description` | Trim text | Official release description. |
| Inventory dataset ID | `reference_version` | Constant `icd10cm_fy2027` | Required lineage. |
| Inventory effective start | `reference_effective_start` | Date `2026-10-01` | Release-level validity. |
| Inventory effective end | `reference_effective_end` | Date `2027-09-30` | Release-level validity. |
| Source member name | `source_member` | Constant | Lineage. |

A claim diagnosis may be validated only when its code system is known or explicitly approved as ICD-10-CM and its service date falls within the reference period. Otherwise the result is `unknown_code_system` or `reference_version_unavailable`, not invalid.

## 6. CMS HCPCS Level II mapping

Source member: `HCPC2026_OCT_ANWEB_09232026.xlsx`. Logical target: `staging.stg_cms_hcpcs`.

| Source field | Intended target field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| `HCPC` | `hcpcs_code` | text; required | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `SEQNUM` | `sequence_number` | text | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `RECID` | `record_identifier` | text | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `LONG DESCRIPTION` | `long_description` | text | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `SHORT DESCRIPTION` | `short_description` | text | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `PRICE1` | `price_1` | numeric; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `PRICE2` | `price_2` | numeric; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `PRICE3` | `price_3` | numeric; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `PRICE4` | `price_4` | numeric; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `MULT_PI` | `multiple_pricing_indicator` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `CIM1` | `coverage_issues_manual_1` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `CIM2` | `coverage_issues_manual_2` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `CIM3` | `coverage_issues_manual_3` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `MCM1` | `medicare_carrier_manual_1` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `MCM2` | `medicare_carrier_manual_2` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `MCM3` | `medicare_carrier_manual_3` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `STATUTE` | `statute` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `LABCERT1` | `lab_certification_1` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `LABCERT2` | `lab_certification_2` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `LABCERT3` | `lab_certification_3` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `LABCERT4` | `lab_certification_4` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `LABCERT5` | `lab_certification_5` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `LABCERT6` | `lab_certification_6` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `LABCERT7` | `lab_certification_7` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `LABCERT8` | `lab_certification_8` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `XREF1` | `cross_reference_1` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `XREF2` | `cross_reference_2` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `XREF3` | `cross_reference_3` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `XREF4` | `cross_reference_4` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `XREF5` | `cross_reference_5` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `COV` | `coverage_code` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `ASC_GRP` | `asc_group` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `ASC_DT` | `asc_effective_date` | date YYYYMMDD; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `OPPS` | `opps_code` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `OPPS_PI` | `opps_payment_indicator` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `OPPS_DT` | `opps_effective_date` | date YYYYMMDD; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `PROCNOTE` | `processing_note_code` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `BETOS` | `betos_code` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `TOS1` | `type_of_service_1` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `TOS2` | `type_of_service_2` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `TOS3` | `type_of_service_3` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `TOS4` | `type_of_service_4` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `TOS5` | `type_of_service_5` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `ANEST_BU` | `anesthesia_base_units` | numeric; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `ADD DT` | `added_date` | date YYYYMMDD; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `ACT EFF DT` | `action_effective_date` | date YYYYMMDD; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `TERM DT` | `termination_date` | date YYYYMMDD; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |
| `ACTION CD` | `action_code` | text; nullable | Retain CMS source semantics; decode indicators only from the supplied record layout. |

Every HCPCS row also receives reference version `hcpcs_2026_q4`, effective start `2026-10-01`, effective end `2026-12-31`, source filename, member name, checksum, and load metadata. Blank termination dates remain blank.

## 7. CMS Medicare Physician Fee Schedule mapping

Primary source member: `PPRRVU2026_Oct_nonQPP.csv`. Logical target: `staging.stg_cms_mpfs`. The CSV has a ten-row presentation header. Source elements below follow the ordered CMS RVU26D data-record layout rather than pandas-generated duplicate names.

| Ordered source element | Intended target field | Type/transform | Use or limitation |
| --- | --- | --- | --- |
| HCPCS Code (position 1) | `hcpcs_code` | text; required | CPT or HCPCS Level II code. |
| Modifier (2) | `modifier` | text; nullable | Blank/global, 26, TC, or supported modifier. |
| Description (3) | `description` | text | CPT text is AMA copyrighted. |
| Status Code (4) | `status_code` | text | Payment policy status. |
| Not Used for Medicare Payment (5) | `medicare_payment_unused` | text/numeric; retain | Header marks this field unused; do not treat as payment. |
| Work RVU (6) | `work_rvu` | numeric; nullable | Physician work component. |
| Non-Facility PE RVU (7) | `nonfacility_pe_rvu` | numeric; nullable | May contain NA. |
| Non-Facility NA Indicator (8) | `nonfacility_na_indicator` | text; nullable | Setting availability indicator. |
| Facility PE RVU (9) | `facility_pe_rvu` | numeric; nullable | May contain NA. |
| Facility NA Indicator (10) | `facility_na_indicator` | text; nullable | Setting availability indicator. |
| Malpractice RVU (11) | `malpractice_rvu` | numeric; nullable | Malpractice component. |
| Total Non-Facility RVUs (12) | `total_nonfacility_rvu` | numeric; nullable | CMS total. |
| Total Facility RVUs (13) | `total_facility_rvu` | numeric; nullable | CMS total. |
| PC/TC Indicator (14) | `pctc_indicator` | text | Professional/technical component policy. |
| Global Surgery (15) | `global_surgery_days` | text | Includes nonnumeric policy values. |
| Preoperative Percentage (16) | `preoperative_percentage` | numeric; nullable | Global-package component. |
| Intraoperative Percentage (17) | `intraoperative_percentage` | numeric; nullable | Global-package component. |
| Postoperative Percentage (18) | `postoperative_percentage` | numeric; nullable | Global-package component. |
| Multiple Procedure Indicator (19) | `multiple_procedure_indicator` | text | Payment policy indicator. |
| Bilateral Surgery Indicator (20) | `bilateral_surgery_indicator` | text | Payment policy indicator. |
| Assistant at Surgery Indicator (21) | `assistant_surgery_indicator` | text | Payment policy indicator. |
| Co-Surgeons Indicator (22) | `cosurgeons_indicator` | text | Payment policy indicator. |
| Team Surgery Indicator (23) | `team_surgery_indicator` | text | Payment policy indicator. |
| Pricing Indicator (24) | `pricing_indicator` | text | QPP applicability indicator in this release. |
| Endoscopic Base Code (25) | `endoscopic_base_code` | text; nullable | Related base procedure code. |
| Conversion Factor (26) | `conversion_factor` | numeric | CMS factor; not a payer contract rate. |
| Physician Supervision of Diagnostic Procedures (27) | `physician_supervision_code` | text | Policy indicator. |
| Calculation Flag (28) | `calculation_flag` | text | CMS calculation flag. |
| Diagnostic Imaging Family Indicator (29) | `diagnostic_imaging_family` | text; nullable | Imaging family policy indicator. |
| Non-Facility PE Used for OPPS Payment (30) | `opps_nonfacility_pe_rvu` | numeric; nullable | OPPS cap comparison input. |
| Facility PE Used for OPPS Payment (31) | `opps_facility_pe_rvu` | numeric; nullable | OPPS cap comparison input. |
| Malpractice Used for OPPS Payment (32) | `opps_malpractice_rvu` | numeric; nullable | OPPS cap comparison input. |

Every MPFS row also receives reference version `mpfs_rvu26d_nonqpp`, effective start `2026-10-01`, effective end `2026-12-31`, source filename, member name, checksum, and load metadata.

The archive also includes QPP, GPCI, locality/county, anesthesia conversion-factor, OPPS-cap, and documentation files. They remain preserved but are not mapped into analytical targets in the current scope. QPP and non-QPP rows must not be unioned without an explicit population discriminator.

## 8. Relationship mapping and unresolved joins

| Relationship | Available evidence | Intended result | Status/limitation |
| --- | --- | --- | --- |
| Patient to encounter | `encounters.PATIENT = patients.Id` | Encounter patient foreign key | Direct identifier relationship; test orphan rate. |
| Encounter to procedure/condition/medication | Source `ENCOUNTER` to `encounters.Id` | Event-to-encounter relationship | Direct identifier relationship; test cardinality and orphans. |
| Encounter to payer | `encounters.PAYER = payers.Id` | Encounter payer foreign key | Direct identifier relationship. |
| Claim to patient | `claims.PATIENTID = patients.Id` | Claim patient foreign key | Direct identifier relationship. |
| Claim to transaction | `claims_transactions.CLAIMID = claims.Id` | Claim transaction foreign key | Direct identifier relationship; test one-to-many and orphans. |
| Transaction to patient | `claims_transactions.PATIENTID = patients.Id` | Transaction patient foreign key | Must agree with linked claim patient; discrepancies are quality exceptions. |
| Encounter to claim | Patient, provider, service date, appointment/code evidence | `int_encounter_claim_matching` | No direct encounter ID exists in selected claims or transaction sources. Composite rule is not yet approved; amount equality is prohibited. |
| Claim diagnosis to ICD-10-CM | Diagnosis field plus service date and known code system | Code validation result | Code system is not explicit; unknown cases must remain unknown. |
| Transaction procedure to HCPCS/MPFS | `PROCEDURECODE`, modifier, service date | Code/reference validation result | CPT versus HCPCS system and historical reference version may be unavailable. |
| Claim insurance ID to payer | Insurance/member IDs and encounter payer | Payer attribution | No documented direct equivalence; do not join by assumption. |

## 9. Fields intentionally not derived

The current sources do not support reliable derivation of:

- contractual allowed amount;
- contractual adjustment category;
- payer-specific expected reimbursement;
- denial reason or appeal outcome;
- cash deposit or general-ledger posting;
- actual write-off reason;
- authoritative claim-to-encounter identifier;
- currency code;
- historical A/R snapshot;
- comprehensive licensed CPT reference; or
- actual hospital revenue leakage.

These must remain unavailable until a source or approved business rule supplies the required evidence.

## 10. Mapping controls

1. Verify source headers or fixed-width layouts before every load.
2. Test required identifiers, uniqueness at the documented grain, and relationship orphans.
3. Retain rejected values and parse errors with source row lineage.
4. Compare raw and staged row counts, excluding only documented rejects.
5. Preserve source amount and sign before classification.
6. Record reference version and effective-date validation outcome for each code check.
7. Prevent current CMS references from being applied to historical service dates outside their effective windows.
8. Do not publish underpayment, denial, or leakage amounts until their missing rule inputs are resolved.
