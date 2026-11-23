# Data sources

## Synthea CSV sample

The Day 3 source is the official Synthea November 2021 1K CSV sample archive:

```text
https://synthetichealth.github.io/synthea-sample-data/downloads/synthea_sample_data_csv_nov2021.zip
```

The archive is pinned with SHA-256:

```text
870b68a127f3570ca964e89e49dd3433cf3e7a27cc4079d2bff5f094be0a43c2
```

The selected source files are `patients.csv`, `encounters.csv`,
`procedures.csv`, `medications.csv`, `conditions.csv`, `claims.csv`,
`claims_transactions.csv`, and `payers.csv`.

Acquire and validate the source files from the repository root:

```powershell
python scripts/download_synthea_data.py
```

Validate files already on disk and refresh their metadata inventory:

```powershell
python scripts/validate_source_files.py
```

The scripts stream large files rather than loading them into memory. Downloaded
CSVs are copied byte-for-byte from the official ZIP into `data/raw/synthea/`.
They are excluded from Git to avoid committing large generated source data. The
tracked `data/raw/synthea/_inventory.json` records source provenance, original
archive member names, file sizes, logical CSV row counts, headers, and SHA-256
checksums.

All Synthea records and financial fields are synthetic. They do not represent
real patients, hospital revenue, contractual reimbursement, or actual financial
performance.

## CMS reference data

Day 4 uses a version-pinned snapshot of CMS files effective on November 23,
2026. The original ZIP files are preserved under `data/raw/cms/`; they are not
extracted or rewritten.

| Dataset | Selected version | Effective period | Official source |
| --- | --- | --- | --- |
| ICD-10-CM diagnoses | FY 2027 code descriptions | 2026-10-01 through 2027-09-30 | [CMS ICD-10 files](https://www.cms.gov/medicare/coding-billing/ICD-10-codes) |
| HCPCS Level II | October 2026 quarterly file | 2026-10-01 through 2026-12-31 | [CMS HCPCS quarterly update](https://www.cms.gov/medicare/coding-billing/healthcare-common-procedure-system/quarterly-update) |
| Medicare Physician Fee Schedule | RVU26D October release | 2026-10-01 through 2026-12-31 | [CMS RVU26D](https://www.cms.gov/medicare/payment/fee-schedules/physician/pfs-relative-value-files/rvu26d) |

The January 2027 HCPCS and RVU27A files were already published on the acquisition
date but were future-effective. They were not selected for this as-of-date
snapshot. Re-run acquisition only after intentionally reviewing and updating the
pinned version metadata and checksums.

Download and validate the selected source archives:

```powershell
python scripts/download_cms_data.py
```

Validate existing archives without downloading:

```powershell
python scripts/download_cms_data.py --validate-only
```

The tracked `data/raw/cms/_inventory.json` records source URLs, version and
effective dates, file sizes, archive members, and SHA-256 checksums. The original
ZIP files are ignored by Git.

### Format and licensing limitations

- ICD-10-CM descriptions are headerless fixed-width text. Codes omit display
  decimals and have no row-level effective dates.
- HCPCS Level II is supplied as fixed-width text and Excel, with code-level add,
  active-effective, and termination dates.
- RVU26D includes CSV, text, Excel, and PDF files. Its main RVU CSV uses a
  multi-row header and does not contain row-level effective dates.
- CPT Level I codes and descriptions are owned by the American Medical
  Association. The MPFS archive contains CMS-authorized CPT/HCPCS references for
  Medicare payment use, but this project does not claim a comprehensive licensed
  CPT reference set.
- Medicare RVUs and payment indicators are reference values, not contractual
  payer reimbursement amounts or evidence of underpayment.
