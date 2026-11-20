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
