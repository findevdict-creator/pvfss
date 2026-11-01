# PVFSS ERP

Custom Frappe app `pvfss` for PVFSS Solutions LLC, built by Quantum-Electro Pvt Ltd on ERPNext v16.
Every customisation lives in this app (GEN-01, GEN-02): no core edits and no UI-only changes.

## Pinned versions

| Component | Version |
|---|---|
| Frappe | v16.54.0 |
| ERPNext | v16.53.0 |
| Python | 3.14 |
| Node | 24 |
| MariaDB | 11.8 (CI) |

Change these together in `.github/workflows/ci.yml` and here. Never deploy the `develop` branch.

## Install (developer bench)

```bash
bench init frappe-bench --frappe-branch v16.54.0
cd frappe-bench
bench get-app erpnext https://github.com/frappe/erpnext --branch v16.53.0
bench get-app https://github.com/findevdict-creator/pvfss
bench new-site pvfss.localhost --install-app erpnext
bench --site pvfss.localhost install-app pvfss
bench --site pvfss.localhost set-config developer_mode 1
bench --site pvfss.localhost set-config pvfss_skip_2fa 1   # local dev only; staging/prod keep 2FA (GEN-63)
```

## Build steps

The app is built module by module. Each step is a branch cut from the previous one and is
merged to `main` at the end after review.

| Branch | Scope |
|---|---|
| `01-platform` | App skeleton and module defs, hooks, PVFSS Settings, Import Exception Log, gate framework, settings accessor, alert sender, roles, Track Changes, security defaults, CI |
| `02-masters` | Company, currencies, taxes, naming series, Customer / Item / Employee fields, shared line fields (GEN-50), Client Project, Inspection Agency, warehouses, lost reasons |
| `03-theme` | Theme tokens (light / dark), logo, login, letterhead and print style |
| `04-crm` | Module 1: Inquiry (Opportunity) and CRM |
| `05-supplier` | Module 2: supplier management, AVL, evaluation |
| `06-rfq` | Module 3: RFQ, supplier quotations, competitive statement, costing, technical evaluation (G1) |
| `07-quotation` | Module 4: quotation approval by margin (G2), Customer PO review |
| `08-purchasing` | Module 5: Supplier PO, compliance check (G3), deviations, approvals |
| `09-project` | Module 6: handover (G4), project execution, expediting, closure |
| `10-traceability` | Module 9: Heat Number + Batch model, receipt rule (G6) |
| `11-smr` | Module 7: SMR, tally sheet, MTC age rules |
| `12-quality` | Module 8: submittals, ITP, RFI, inspection, MTC, NCR, IRN (G5) |
| `13-dispatch` | Module 10: Delivery Note, dispatch gate (G7), documents, POD |
| `14-finance` | Module 11: invoicing, payments, LC, PDC, retention, VAT, cash flow |
| `15-hse` | Module 12: HSE |
| `16-icv` | Module 13: ICV |
| `17-dms` | Module 14: project documents |
| `18-reports` | Module 15: workspaces, dashboards, reports |

## Conventions

- Custom fields on standard DocTypes are prefixed `pvfss_` (GEN-03) and carry module `PVFSS…` so fixtures pick them up.
- Logic on standard DocTypes goes through `doc_events` → `pvfss/overrides/<doctype>.py` (GEN-04).
- Every [RULE] is enforced server-side (GEN-05) using `pvfss.gates.base.GateResult`, which collects every failure into one dialog and logs instead of blocking during a PVFSS historical import (IMP-01).
- Thresholds are read through `pvfss.utils.settings` from **PVFSS Settings**, never hard-coded (GEN-06).
- Each [RULE] has a test named after its requirement ID, e.g. `test_IMP_01_import_logs_instead_of_blocking` (GEN-07).
- Scheduled alerts are registered in `pvfss/tasks.py` and sent with `pvfss.utils.alerts.send` (bell + email, GEN-61).

### Historical imports (IMP-01)

Gates are skipped, and logged to **Import Exception Log**, only when:

- code runs inside `with pvfss.utils.importing.pvfss_import():`, or
- a standard Data Import has **Historical load: skip PVFSS rules and log them** ticked.

## Tests and CI

```bash
bench --site pvfss.localhost set-config allow_tests true
bench --site pvfss.localhost run-tests --app pvfss
```

CI (`.github/workflows/ci.yml`) installs the pinned Frappe and ERPNext, installs this app on a fresh
site, runs the tests and then the **fixture drift check** (GEN-02): it re-exports fixtures and fails if
they differ from what is committed.

Code style: `pre-commit install` (ruff, prettier, eslint).

## License

GPL-3.0. Keep GPL notices (GEN-08).
