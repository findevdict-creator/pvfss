"""Scheduled alerts (GEN-61, requirements §20.3).

Each module branch appends its alert functions to DAILY or HOURLY as dotted paths.
One failing alert is logged and never stops the others.
"""

import frappe

DAILY = [
	"pvfss.pvfss_crm.alerts.inquiry_due_date",  # CRM-12
	"pvfss.pvfss_crm.supplier_alerts.document_expiry",  # SUP-04
	"pvfss.pvfss_purchasing.project.delay_alerts",  # PRJ-21
	"pvfss.utils.mtc_age.age_alerts",  # SMR-21
	"pvfss.overrides.non_conformance.overdue_alerts",  # QA-31
	"pvfss.pvfss_logistics.dispatch.pod_alerts",  # DSP-10
	"pvfss.pvfss_finance.alerts.lc_alerts",  # FIN-41
	"pvfss.pvfss_finance.alerts.pdc_alerts",  # FIN-45
	"pvfss.pvfss_finance.alerts.retention_alerts",  # FIN-52
	"pvfss.pvfss_hse.alerts.training_expiry",  # HSE-31
	"pvfss.pvfss_hse.alerts.capa_overdue",  # HSE-31
	"pvfss.pvfss_hse.alerts.risk_review",  # HSE-02, HSE-03
	"pvfss.pvfss_icv.icv.daily",  # ICV-03, ICV-11
]

HOURLY = [
	"pvfss.pvfss_hse.alerts.investigation_overdue",  # HSE-31
	"pvfss.pvfss_hse.alerts.permit_expiry",  # HSE-10
]


def _run(jobs):
	for path in jobs:
		try:
			frappe.get_attr(path)()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=f"PVFSS alert failed: {path}")


def daily_alerts():
	_run(DAILY)


def hourly_alerts():
	_run(HOURLY)
