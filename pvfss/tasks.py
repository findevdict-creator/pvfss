"""Scheduled alerts (GEN-61, requirements §20.3).

Each module branch appends its alert functions to DAILY or HOURLY as dotted paths.
One failing alert is logged and never stops the others.
"""

import frappe

DAILY = [
	"pvfss.pvfss_crm.alerts.inquiry_due_date",  # CRM-12
	"pvfss.pvfss_crm.supplier_alerts.document_expiry",  # SUP-04
]

HOURLY = [
	# "pvfss.pvfss_hse.alerts.investigation_overdue",  # HSE-31 (15-hse)
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
